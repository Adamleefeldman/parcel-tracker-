/**
 * Direct-to-storage binary upload (step 2 of the presigned-URL flow).
 *
 * The presign endpoint hands back a short-lived R2 PUT URL signed for a
 * specific `Content-Type`. We PUT the raw file bytes straight to that URL —
 * never through our own API server — with the SAME `Content-Type` string the
 * presign was signed with. A mismatch breaks the signature and R2 rejects the
 * PUT, so the caller MUST thread one `mime_type` value presign → here → confirm.
 *
 * Native file I/O is isolated to this module. We use `expo-file-system`'s
 * LEGACY API (`expo-file-system/legacy`) — SDK 54's new `File`/`Directory`
 * surface has no binary-PUT-with-progress equivalent, and Expo ships the
 * legacy import explicitly for exactly this case. `createUploadTask` streams
 * the file from disk (no loading the whole thing into JS memory) and reports
 * progress.
 */

import { createUploadTask, FileSystemUploadType } from 'expo-file-system/legacy';

export interface PutFileArgs {
  /** The presigned PUT URL from `POST /documents/upload-url`. */
  url: string;
  /** Local `file://` URI of the picked file. */
  fileUri: string;
  /** MUST equal the `mime_type` sent at presign (it's in the signature). */
  contentType: string;
  /** Progress callback, 0..1. Only fires when the platform reports a total. */
  onProgress?: (fraction: number) => void;
}

/**
 * PUT a local file's bytes to a presigned URL. Resolves on a 2xx response,
 * throws on any other status (so the caller surfaces an inline error and the
 * confirm step never runs against a failed upload).
 */
export async function putFile({
  url,
  fileUri,
  contentType,
  onProgress,
}: PutFileArgs): Promise<void> {
  const task = createUploadTask(
    url,
    fileUri,
    {
      httpMethod: 'PUT',
      uploadType: FileSystemUploadType.BINARY_CONTENT,
      headers: { 'Content-Type': contentType },
    },
    (data) => {
      if (onProgress && data.totalBytesExpectedToSend > 0) {
        const fraction = data.totalBytesSent / data.totalBytesExpectedToSend;
        onProgress(Math.max(0, Math.min(1, fraction)));
      }
    },
  );

  const result = await task.uploadAsync();
  // `uploadAsync` resolves undefined/null if the task was cancelled.
  if (!result) {
    throw new Error('Upload was cancelled.');
  }
  if (result.status < 200 || result.status >= 300) {
    throw new Error(`Upload failed (status ${result.status}).`);
  }
}
