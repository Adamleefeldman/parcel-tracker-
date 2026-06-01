/**
 * Wiring test for the document-upload orchestration. Same strategy as the
 * other mutation tests: stub the React Query hooks so the hook returns its
 * options object, mock `authedApiRequest` + `putFile`, then probe the three
 * steps of `mutationFn` and `onSuccess`.
 *
 * The reviewer-critical assertions: confirm sends entity_type/entity_id as
 * QUERY params (not body), and NO document endpoint carries an Idempotency-Key.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));
jest.mock('../../lib/upload', () => ({ putFile: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import { putFile } from '../../lib/upload';
import { useUploadDocument } from './useUploadDocument';

const mockAuthed = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;
const mockPutFile = putFile as jest.MockedFunction<typeof putFile>;

const vars = {
  fileUri: 'file:///tmp/inv.pdf',
  fileName: 'inv.pdf',
  contentType: 'application/pdf',
  fileSize: 2048,
};

describe('useUploadDocument', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPutFile.mockResolvedValue(undefined);
  });

  it('runs presign → PUT → confirm with the right shapes', async () => {
    mockAuthed
      .mockResolvedValueOnce({
        upload_url: 'https://r2.example/put',
        file_key: 'invoice/e-1/abc_inv.pdf',
        expires_in_seconds: 300,
      } as never)
      .mockResolvedValueOnce({ id: 'd-1' } as never);

    const mutation = useUploadDocument('invoice', 'e-1') as any;
    await mutation.mutationFn(vars);

    // 1. presign — entity_type/entity_id in the BODY here
    expect(mockAuthed).toHaveBeenNthCalledWith(1, '/api/v1/documents/upload-url', {
      method: 'POST',
      body: {
        entity_type: 'invoice',
        entity_id: 'e-1',
        file_name: 'inv.pdf',
        mime_type: 'application/pdf',
        file_size_bytes: 2048,
      },
    });

    // 2. PUT — same Content-Type the presign was signed with
    expect(mockPutFile).toHaveBeenCalledWith({
      url: 'https://r2.example/put',
      fileUri: 'file:///tmp/inv.pdf',
      contentType: 'application/pdf',
      onProgress: undefined,
    });

    // 3. confirm — entity_type/entity_id are QUERY params; body has neither
    expect(mockAuthed).toHaveBeenNthCalledWith(
      2,
      '/api/v1/documents/confirm?entity_type=invoice&entity_id=e-1',
      {
        method: 'POST',
        body: {
          file_key: 'invoice/e-1/abc_inv.pdf',
          file_name: 'inv.pdf',
          mime_type: 'application/pdf',
          file_size_bytes: 2048,
        },
      },
    );
    const confirmBody = mockAuthed.mock.calls[1][1]?.body as Record<string, unknown>;
    expect(confirmBody).not.toHaveProperty('entity_type');
    expect(confirmBody).not.toHaveProperty('entity_id');
  });

  it('sends NO Idempotency-Key on any document endpoint', async () => {
    mockAuthed
      .mockResolvedValueOnce({
        upload_url: 'https://r2.example/put',
        file_key: 'k',
        expires_in_seconds: 300,
      } as never)
      .mockResolvedValueOnce({ id: 'd-1' } as never);

    const mutation = useUploadDocument('invoice', 'e-1') as any;
    await mutation.mutationFn(vars);

    for (const call of mockAuthed.mock.calls) {
      const options = call[1] ?? {};
      expect(options).not.toHaveProperty('headers');
    }
  });

  it('passes onProgress through to putFile', async () => {
    mockAuthed
      .mockResolvedValueOnce({ upload_url: 'u', file_key: 'k', expires_in_seconds: 300 } as never)
      .mockResolvedValueOnce({ id: 'd-1' } as never);
    const onProgress = jest.fn();

    const mutation = useUploadDocument('invoice', 'e-1') as any;
    await mutation.mutationFn({ ...vars, onProgress });

    expect(mockPutFile).toHaveBeenCalledWith(expect.objectContaining({ onProgress }));
  });

  it('omits file_size_bytes when the size is unknown', async () => {
    mockAuthed
      .mockResolvedValueOnce({ upload_url: 'u', file_key: 'k', expires_in_seconds: 300 } as never)
      .mockResolvedValueOnce({ id: 'd-1' } as never);

    const mutation = useUploadDocument('payment', 'p-9') as any;
    await mutation.mutationFn({ ...vars, fileSize: undefined });

    const presignBody = mockAuthed.mock.calls[0][1]?.body as Record<string, unknown>;
    expect(presignBody).not.toHaveProperty('file_size_bytes');
  });

  it('invalidates the documents list for the entity on success', () => {
    const mutation = useUploadDocument('bill_of_lading', 'bl-3') as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['documents', 'bill_of_lading', 'bl-3'],
    });
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
  });
});
