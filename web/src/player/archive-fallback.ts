// archive.org's /download/ links redirect to whichever copy of an item its
// balancer picks. Some mirror copies are broken (the file answers 500) while
// the item's primary servers still serve it, so a track that fails to load
// gets a second chance at the servers archive.org's metadata names.

const DOWNLOAD = /^https?:\/\/archive\.org\/download\/([^/?#]+)\/([^?#]+)/;

type ArchiveMetadata = { d1?: unknown; d2?: unknown; dir?: unknown };

export async function archiveFallbackUrls(url: string, fetcher: typeof fetch = fetch): Promise<string[]> {
  const match = DOWNLOAD.exec(url);
  if (!match) return [];
  const [, item, file] = match;
  try {
    const response = await fetcher(`https://archive.org/metadata/${item}`);
    if (!response.ok) return [];
    const metadata = (await response.json()) as ArchiveMetadata;
    if (typeof metadata.dir !== "string") return [];
    const dir = metadata.dir;
    const hosts = [metadata.d1, metadata.d2].filter((host): host is string => typeof host === "string" && host.length > 0);
    return [...new Set(hosts)].map((host) => `https://${host}${dir}/${file}`);
  } catch {
    return [];
  }
}
