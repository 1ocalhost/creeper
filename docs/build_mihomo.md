# Build Mihomo

## patch

Allow listening on port 0

> Mihomo uses port 0 to disable the listener internally. We're removing this
  restriction when creating the mixed listener, assuming that it will
  definitely be started.

```go
// listener/listener.go

func ReCreateMixed(port int, tunnel C.Tunnel) {
	// if portIsZero(addr) {
	// 	return
	// }
}
```

Fix speed test failures

> Since handleTCPConn() depends on the 'Running' state, the port might start
  listening prematurely and fail to process proxy requests, leading to errors
  during speed tests.

```go
// hub/executor/executor.go

func ApplyConfig(cfg *config.Config, force bool) {
	tunnel.OnRunning()

	// Move this after tunnel.OnRunning().
	updateListeners(cfg.General, cfg.Listeners, force)
}
```

## build

```shell
make windows-amd64
```
