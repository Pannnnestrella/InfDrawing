/**
 * Normalize image URLs for tldraw asset `src`.
 * Current tldraw rejects `blob:` as an invalid protocol.
 */

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error("failed to encode image as data URL"));
    };
    reader.onerror = () => reject(new Error("failed to read image blob"));
    reader.readAsDataURL(blob);
  });
}

/** Convert blob:/relative URLs into data: or absolute http(s) for tldraw assets. */
export async function toTldrawCompatibleSrc(imageUrl: string): Promise<string> {
  if (imageUrl.startsWith("data:")) return imageUrl;
  if (imageUrl.startsWith("http://") || imageUrl.startsWith("https://")) {
    return imageUrl;
  }
  if (imageUrl.startsWith("/") && typeof window !== "undefined") {
    return `${window.location.origin}${imageUrl}`;
  }
  if (imageUrl.startsWith("blob:")) {
    const response = await fetch(imageUrl);
    if (!response.ok) {
      throw new Error(`failed to read blob image: ${response.status}`);
    }
    return blobToDataUrl(await response.blob());
  }
  const response = await fetch(imageUrl);
  if (!response.ok) {
    throw new Error(`failed to fetch image for canvas: ${response.status}`);
  }
  return blobToDataUrl(await response.blob());
}
