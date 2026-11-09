// osint-cli: backend of FlipperOne-OSINT.
// Usage: osint-cli <type> <value> [extra]
// Infrastructure types: username, email, phone, domain, ip
// Person types (via PersonIntel): person-email, person-username, person-phone,
//
//	person-name, person-report, pi-status, pi-case, pi-report, pi-graph
//
// Output: one line per result, first character = marker:
//   - found   - not found   ! warning/unclear   i info   # section heading
//     = proven  ~ indication  ? unconfirmed  (evidence level of a person finding)
//
// "extra" carries the confirmation of an active check, which the UI has obtained from the
// person at the device ("confirm"). Without it, active person checks are refused.
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

// Set at build time via -ldflags "-X main.Version=...".
var Version = "dev"

const userAgent = "Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0"

var outMu sync.Mutex

// store ist das gemeinsame Ergebnis- und Graphmodell beider Haelften (siehe findings.go).
var store = NewStore()

var asciiRepl = strings.NewReplacer(
	"ä", "ae", "ö", "oe", "ü", "ue", "Ä", "Ae", "Ö", "Oe", "Ü", "Ue", "ß", "ss",
	"–", "-", "—", "-", "―", "-", "‐", "-",
	"’", "'", "‘", "'", "‚", "'", "′", "'",
	"“", "\"", "”", "\"", "„", "\"", "«", "\"", "»", "\"", "″", "\"",
	"…", "...", "•", "*", "·", "-", "→", "->", "←", "<-", "±", "+/-",
	"€", "EUR", "£", "GBP", "°", "deg", "×", "x", "™", "(TM)", "©", "(c)", "®", "(R)",
	"\u00a0", " ", "\u202f", " ", "\u2009", " ",
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
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "Usage: osint-cli <username|email|phone|domain|ip> <value>")
		os.Exit(2)
	}
	typ := strings.ToLower(os.Args[1])
	val := strings.TrimSpace(os.Args[2])
	extra := ""
	if len(os.Args) >= 4 {
		extra = strings.ToLower(strings.TrimSpace(os.Args[3]))
	}
	if val == "" || len(val) > 200 {
		warn("Input empty or too long")
		os.Exit(0)
	}
	confirmed := extra == "confirm" || extra == "confirmed"

	// Safety net: stop after 150 seconds.
	go func() {
		time.Sleep(150 * time.Second)
		warn("Aborted: time limit reached (150s)")
		os.Exit(0)
	}()

	switch typ {
	// --- infrastructure (unchanged behaviour) ---
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
	// --- new unified entry types; sources remain separate and attributable ---
	case "ipv4":
		runTypedIP(val, false)
	case "ipv6":
		runTypedIP(val, true)
	case "website":
		runWebInput(val)
	case "gps":
		runGPS(val)
	case "address":
		runAddress(val)
	case "company", "organization":
		runOrganization(val)
	case "registry":
		runRegistry(val)
	case "plate":
		runPlate(val)
	case "vin":
		runVIN(val)
	case "wallet":
		runWallet(val)
	case "asn":
		runASN(val)

	// --- person research through PersonIntel ---
	case "pi-status":
		runPIStatus()
	case "pi-case":
		runPICase(val)
	case "pi-report":
		runPIReport(val)
	case "pi-graph":
		runPIGraph()
	// --- combined: infrastructure and person modules in one run, merged ---
	case "combo-username":
		runUsername(val)
		runPerson("username", val, confirmed, store)
	case "combo-email":
		runEmail(val)
		runPerson("email", val, confirmed, store)
	case "combo-phone":
		runPhone(val)
		runPerson("phone", val, confirmed, store)

	case "person-email":
		runPerson("email", val, confirmed, store)
	case "person-username":
		runPerson("username", val, confirmed, store)
	case "person-phone":
		runPerson("phone", val, confirmed, store)
	case "person-name":
		runPublicName(val)
	case "vendor-name":
		runPerson("name", val, confirmed, store)
	case "person-report":
		runPerson("report_file", val, confirmed, store)
	default:
		warn("Unknown type: %s", typ)
	}

	// The shared model only prints when something was collected, so the output of the
	// infrastructure modules stays exactly as it was when nothing feeds it.
	store.PrintSummary()
	store.PrintGraph()
	store.PrintFollowUps(12)
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

// nowISO liefert den Zeitstempel für Herkunftsnachweise (UTC, Sekunden).
func nowISO() string { return time.Now().UTC().Format("2006-01-02T15:04:05Z07:00") }
