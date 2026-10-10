export const ALLOWED_RECEIPT_TYPES = ['image/jpeg', 'image/png', 'application/pdf'];
export const MAX_RECEIPT_BYTES = 5 * 1024 * 1024;

/** Client-side pre-check mirroring the contract's codes, so the form can
 * give inline feedback before ever hitting the network. The server still
 * checks the file's actual content, not just its declared type — this is
 * just the fast, friendly first pass. */
export function validateReceiptFile(file: File): { field: string; code: string; message: string } | null {
  if (!ALLOWED_RECEIPT_TYPES.includes(file.type)) {
    return { field: 'receipt_file', code: 'unsupported_file_type', message: 'Receipts must be a JPG, PNG or PDF.' };
  }
  if (file.size > MAX_RECEIPT_BYTES) {
    return { field: 'receipt_file', code: 'file_too_large', message: 'Receipts must be 5 MB or smaller.' };
  }
  return null;
}
