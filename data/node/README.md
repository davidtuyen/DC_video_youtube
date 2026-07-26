# Portable Node runtime

`node.exe` is bundled with the Windows application so yt-dlp can solve
YouTube JavaScript challenges without requiring a system-wide Node install.

The build scripts create `data/node/node.exe` from the Node executable on the
build machine when it is missing. Node 22 or newer is required by yt-dlp.

The current bundled development runtime is Node v24.12.0. See `LICENSE` for
Node.js and third-party license notices.
