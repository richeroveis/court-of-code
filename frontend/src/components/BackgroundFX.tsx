// Atmospheric animated background: a slow-drifting perspective grid plus three
// blurred gradient blobs and a faint scanline. Purely decorative and non-interactive.
export default function BackgroundFX() {
  return (
    <div className="bgfx" aria-hidden="true">
      <div className="bgfx-grid" />
      <div className="bgfx-blob blob-a" />
      <div className="bgfx-blob blob-b" />
      <div className="bgfx-blob blob-c" />
      <div className="bgfx-scan" />
    </div>
  );
}
