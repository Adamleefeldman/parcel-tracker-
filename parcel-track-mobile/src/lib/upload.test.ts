/**
 * Behaviour test for `putFile` — the only place native file I/O happens. We
 * mock `expo-file-system/legacy`'s `createUploadTask` so node-env jest never
 * touches the native module, then assert the PUT shape (method + Content-Type
 * header threaded from the presign), progress mapping, and the non-2xx throw.
 */

const uploadAsyncMock = jest.fn();
const createUploadTaskMock = jest.fn();

jest.mock('expo-file-system/legacy', () => ({
  FileSystemUploadType: { BINARY_CONTENT: 0, MULTIPART: 1 },
  createUploadTask: (...args: unknown[]) => createUploadTaskMock(...args),
}));

import { putFile } from './upload';

type ProgressCb = (data: { totalBytesSent: number; totalBytesExpectedToSend: number }) => void;

function lastProgressCallback(): ProgressCb {
  const call = createUploadTaskMock.mock.calls.at(-1);
  return call?.[3] as ProgressCb;
}

describe('putFile', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    createUploadTaskMock.mockImplementation(() => ({ uploadAsync: uploadAsyncMock }));
  });

  it('PUTs with the BINARY_CONTENT upload type and the Content-Type from presign', async () => {
    uploadAsyncMock.mockResolvedValue({ status: 200, body: '', headers: {} });

    await putFile({
      url: 'https://r2.example/upload',
      fileUri: 'file:///tmp/doc.pdf',
      contentType: 'application/pdf',
    });

    expect(createUploadTaskMock).toHaveBeenCalledWith(
      'https://r2.example/upload',
      'file:///tmp/doc.pdf',
      {
        httpMethod: 'PUT',
        uploadType: 0, // FileSystemUploadType.BINARY_CONTENT
        headers: { 'Content-Type': 'application/pdf' },
      },
      expect.any(Function),
    );
    expect(uploadAsyncMock).toHaveBeenCalledTimes(1);
  });

  it('maps native progress to a 0..1 fraction', async () => {
    uploadAsyncMock.mockResolvedValue({ status: 200, body: '', headers: {} });
    const onProgress = jest.fn();

    await putFile({
      url: 'https://r2.example/upload',
      fileUri: 'file:///tmp/doc.pdf',
      contentType: 'application/pdf',
      onProgress,
    });

    const cb = lastProgressCallback();
    cb({ totalBytesSent: 50, totalBytesExpectedToSend: 100 });
    cb({ totalBytesSent: 100, totalBytesExpectedToSend: 100 });

    expect(onProgress).toHaveBeenNthCalledWith(1, 0.5);
    expect(onProgress).toHaveBeenNthCalledWith(2, 1);
  });

  it('does not divide by zero when the total is unknown', async () => {
    uploadAsyncMock.mockResolvedValue({ status: 200, body: '', headers: {} });
    const onProgress = jest.fn();

    await putFile({
      url: 'https://r2.example/upload',
      fileUri: 'file:///tmp/doc.pdf',
      contentType: 'application/pdf',
      onProgress,
    });

    lastProgressCallback()({ totalBytesSent: 0, totalBytesExpectedToSend: 0 });
    expect(onProgress).not.toHaveBeenCalled();
  });

  it('throws on a non-2xx upload status', async () => {
    uploadAsyncMock.mockResolvedValue({ status: 403, body: 'denied', headers: {} });

    await expect(
      putFile({
        url: 'https://r2.example/upload',
        fileUri: 'file:///tmp/doc.pdf',
        contentType: 'application/pdf',
      }),
    ).rejects.toThrow(/403/);
  });

  it('throws when the task resolves empty (cancelled)', async () => {
    uploadAsyncMock.mockResolvedValue(null);

    await expect(
      putFile({
        url: 'https://r2.example/upload',
        fileUri: 'file:///tmp/doc.pdf',
        contentType: 'application/pdf',
      }),
    ).rejects.toThrow(/cancel/i);
  });
});
