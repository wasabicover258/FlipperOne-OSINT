// osint-cli: Backend von FlipperOne-OSINT.
// Aufruf: osint-cli <typ> <wert>
// Typen: username, email, phone, domain, ip, name
// Ausgabe: eine Zeile pro Ergebnis, erstes Zeichen = Markierung:
//   - gefunden   - nicht gefunden   ! Warnung/unklar   i Info   # Abschnittsueberschrift
package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// Wird beim Bauen per -ldflags "-X main.Version=..." gesetzt.
var Version = "dev"

const userAgent = "Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0"

var outMu sync.Mutex

var asciiRepl = strings.NewReplacer(
	"ä", "ae", "ö", "oe", "ü", "ue", "Ä", "Ae", "Ö", "Oe", "Ü", "Ue", "ß", "ss",
	"–", "-", "—", "-", "’", "'", "“", "\"", "”", "\"", "…", "...",
)

// ascii macht Text darstellbar fuer die Oberflaeche (nur ASCII 32..126).
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

// get holt eine URL (max. 512 KB Inhalt).
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
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "Aufruf: osint-cli <username|email|phone|domain|ip|name> <wert>")
		os.Exit(2)
	}
	typ := strings.ToLower(os.Args[1])
	val := strings.TrimSpace(os.Args[2])
	if val == "" || len(val) > 200 {
		warn("EINGABE LEER ODER ZU LANG")
		os.Exit(0)
	}

	// Sicherheitsnetz: nach 100 Sekunden beenden.
	go func() {
		time.Sleep(100 * time.Second)
		warn("ABBRUCH: ZEITLIMIT ERREICHT")
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
	case "name":
		runName(val)
	default:
		warn("UNBEKANNTER TYP: %s", typ)
	}
}

// ipsOf loest einen Namen in IP-Adressen auf.
func ipsOf(host string) []string {
	ctx, cancel := dnsCtx(6)
	defer cancel()
	addrs, err := net.DefaultResolver.LookupHost(ctx, host)
	if err != nil {
		return nil
	}
	return addrs
}
