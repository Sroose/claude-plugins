# Server side — running whisper-server

The `transcribe` skill is a **client**. It needs a [whisper.cpp](https://github.com/ggerganov/whisper.cpp)
`whisper-server` reachable over HTTP. The server can run on the same machine as the client or on
a separate, beefier one.

## 1. Build whisper.cpp and get a model
```
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
cmake -B build && cmake --build build -j --config Release
./models/download-ggml-model.sh large-v3      # or: base, small, medium, large-v3-q5 …
```

Preferably use large-v3 if your memory allows it, else recommended to fall back to the quantized q5 version, not the turbo.

## 2. Start the server
```
./build/bin/whisper-server -m models/ggml-large-v3.bin -nt -mc 64 --carry-initial-prompt --host 0.0.0.0 --port 8777
```
- `--host 127.0.0.1` → only this machine can reach it (use when client + server are the same Mac).
- `--host 0.0.0.0`   → reachable from other machines (use only on a trusted LAN / tailnet).
- `-mc 64` (`--max-context`) caps carried-over text context per window — curbs the repetition/
  drift loops whisper can fall into on long recordings. `--carry-initial-prompt` always re-prepends
  the prompt, so a `--prompt` vocab hint keeps biasing spelling across the whole recording (the
  client sends `carry_initial_prompt=true` per request to match). These two match the LaunchAgent
  template in this folder.
- Per-request params (`language`, `prompt`, `carry_initial_prompt`, …) are sent by the client, so
  you don't have to bake your language into the server command.

Smoke-test it:
```
curl -sS -F file=@samples/jfk.wav -F response_format=text http://127.0.0.1:8777/inference
```

## 3. (macOS, optional) keep it running across reboots
Use `whisper-server.plist.template` in this folder: replace the four placeholders, then load it as
a LaunchAgent (instructions + a per-placeholder table are in the template's header).

Quick reference — the placeholders are literal strings, replace them in place:

| Placeholder       | What goes there                                                                 | Example                                  |
| ----------------- | ------------------------------------------------------------------------------- | ---------------------------------------- |
| `__WHISPER_DIR__` | absolute path to your whisper.cpp checkout                                      | `/Users/you/code/tools/whisper.cpp`      |
| `__MODEL__`       | the model **filename inside `models/`** — basename WITH the `.bin` extension    | `ggml-large-v3.bin` (or `…-q5_0.bin`)    |
| `__HOST__`        | `127.0.0.1` (same-machine only) or `0.0.0.0` (LAN/tailnet)                      | `127.0.0.1`                              |
| `__PORT__`        | TCP port to listen on                                                           | `8777`                                   |

On Linux, a systemd unit does the same job.

## 4. Point the client at it
On first `/transcribe`, the skill asks for the server URL and remembers it. Change it anytime:
```
bash skills/transcribe/transcribe-config.sh set-server http://<host>:8777
```

> ⚠️ **Security:** whisper-server has no authentication. Keep it on localhost or a trusted
> LAN/tailnet, never exposed to the internet.
