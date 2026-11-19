// osint-cli: backend of FlipperOne-OSINT.
// Run without arguments for usage. Classic modes print one line per
// result, first character = marker:
//   - found   - not found   ! warning/unclear   i info   # section heading
//
// The engine modes (deep, watch) work on structured findings (finding.go)
// and render them in the same marker format for the UI, or as JSON.
package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Set at build time via -ldflags "-X main.Version=...".
var Version = "dev"

const userAgent = "Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0"

var outMu sync.Mutex

var asciiRepl = strings.NewReplacer(
	"ä", "ae", "ö", "oe", "ü", "ue", "Ä", "Ae", "Ö", "Oe", "Ü", "Ue", "ß", "ss",
	"–", "-", "—", "-", "’", "'", "“", "\"", "”", "\"", "…", "...",
)

// ascii makes text displayable in the UI (ASCII 32..126 only).
func ascii(s string) string {
	s = asciiRepl.Replace(s)
	var b strings.Builder
	for _, r := range s {
		if r == '\t' {
			b.WriteString("  ")
			continue
		}
		if r < 32 || r > 126 {
			b.WriteByte('?')
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

func emit(marker, s string) {
	outMu.Lock()
	defer outMu.Unlock()
	fmt.Fprintf(os.Stdout, "%s %s\n", marker, ascii(s))
}

func found(f string, a ...any) { emit("+", fmt.Sprintf(f, a...)) }
func miss(f string, a ...any)  { emit("-", fmt.Sprintf(f, a...)) }
func warn(f string, a ...any)  { emit("!", fmt.Sprintf(f, a...)) }
func info(f string, a ...any)  { emit("i", fmt.Sprintf(f, a...)) }
func head(f string, a ...any)  { emit("#", fmt.Sprintf(f, a...)) }

var client = &http.Client{
	Timeout: 10 * time.Second,
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return http.ErrUseLastResponse
		}
		return nil
	},
}

// get fetches a URL (max. 512 KB of content).
func get(c *http.Client, url string) (*http.Response, []byte, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, nil, err
	}
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Accept", "*/*")
	resp, err := c.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
	return resp, body, nil
}

func dnsCtx(sec int) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), time.Duration(sec)*time.Second)
}

func shorten(s string, n int) string {
	s = strings.Join(strings.Fields(s), " ")
	if len(s) > n {
		return s[:n-3] + "..."
	}
	return s
}

func main() {
	if len(os.Args) >= 2 && os.Args[1] == "version" {
		fmt.Println(Version)
		return
	}
	if len(os.Args) >= 2 && engineCommands[strings.ToLower(os.Args[1])] {
		os.Exit(runEngineCommand(strings.ToLower(os.Args[1]), os.Args[2:]))
	}
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, usage)
		os.Exit(2)
	}
	typ := strings.ToLower(os.Args[1])
	val := strings.TrimSpace(os.Args[2])
	if val == "" || len(val) > 200 {
		warn("Input empty or too long")
		os.Exit(0)
	}

	// Watchdog for the classic modes: hard stop after OSINT_TIMEOUT seconds
	// (default 300). The engine commands (deep, watch, ...) use per-module
	// timeouts and a soft deadline instead, so one slow service can no
	// longer kill a whole run.
	limit := envInt("OSINT_TIMEOUT", 300)
	go func() {
		time.Sleep(time.Duration(limit) * time.Second)
		warn("Aborted: time limit reached (%ds, set OSINT_TIMEOUT to change)", limit)
		os.Exit(0)
	}()

	switch typ {
	case "username":
		runUsername(val)
	case "email":
		runEmail(val)
	case "phone":
		runPhone(val)
	case "domain":
		runDomain(val)
	case "ip":
		runIP(val)
	default:
		warn("Unknown type: %s", typ)
	}
}

const usage = `Usage:
  osint-cli <username|email|phone|domain|ip> <value>   classic report
  osint-cli deep <target> [flags]                       entity engine scan
  osint-cli org <name|LEI> | geo <lat,lon|place>        organisation / location scan
  osint-cli watch <add|rm|list|run|scan> [target]       monitoring
  osint-cli cases | export <case> <json|md|graphml|csv> [file]
  osint-cli modules | update-data | version`

func envInt(name string, def int) int {
	if v, err := strconv.Atoi(os.Getenv(name)); err == nil && v > 0 {
		return v
	}
	return def
}

// ipsOf resolves a name to IP addresses.
func ipsOf(host string) []string {
	ctx, cancel := dnsCtx(6)
	defer cancel()
	addrs, err := net.DefaultResolver.LookupHost(ctx, host)
	if err != nil {
		return nil
	}
	return addrs
}
