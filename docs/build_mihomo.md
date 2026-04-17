# Build Mihomo

## patch

Allow listening on port 0

```go
// listener/listener.go

func ReCreateMixed(port int, tunnel C.Tunnel) {
	// if portIsZero(addr) {
	// 	return
	// }
}
```

## build

```shell
make windows-amd64
```
