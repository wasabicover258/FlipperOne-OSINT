package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

var engineCommands = map[string]bool{
	"deep": true, "watch": true, "watchscan": true, "cases": true, "export": true, "modules": true, "update-data": true,
}

var (
	asnRe = regexp.MustCompile(`(?i)^AS\d{1,10}$`)
	cveRe = regexp.MustCompile(`(?i)^CVE-\d{4}-\d{4,}$`)
)

// seedFor detects the entity type of a free-text target.
func seedFor(raw string) (Finding, error) {
	v := strings.TrimSpace(raw)
	switch {
	case net.ParseIP(v) != nil:
		return Finding{Type: KIP, Value: v}, nil
	case asnRe.MatchString(v):
		return Finding{Type: KASN, Value: strings.ToUpper(v)}, nil
	case cveRe.MatchString(v):
		return Finding{Type: KCVE, Value: strings.ToUpper(v)}, nil
	}
	d := normalizeDomain(v)
	if !domainRe.MatchString(d) {
		return Finding{}, fmt.Errorf("not a domain, IP, ASN or CVE: %q", raw)
	}
	if registrableDomain(d) == d {
		return Finding{Type: KDomain, Value: d}, nil
	}
	return Finding{Type: KHost, Value: d}, nil
}

type scanOpts struct {
	depth    int
	deadline int
	workers  int
	modules  string
	exclude  string
	active   bool
}

func (o *scanOpts) register(fs *flag.FlagSet) {
	fs.IntVar(&o.depth, "depth", 4, "max pivot hops from the target")
	fs.IntVar(&o.deadline, "deadline", envInt("OSINT_DEADLINE", 240), "soft time limit for the whole run (s)")
	fs.IntVar(&o.workers, "workers", 8, "parallel module calls")
	fs.StringVar(&o.modules, "modules", "", "only these modules (comma list)")
	fs.StringVar(&o.exclude, "exclude", "", "skip these modules (comma list)")
	fs.BoolVar(&o.active, "active", false, "allow active modules (only against targets you own)")
	fs.BoolVar(&noCache, "fresh", false, "ignore the response cache")
}

func newEngine(o scanOpts, progress bool) *Engine {
	only, skip := csvSet(o.modules), csvSet(o.exclude)
	var mods []*Module
	for _, m := range allModules() {
		if (len(only) == 0 || only[m.Name]) && !skip[m.Name] {
			mods = append(mods, m)
		}
	}
	e := &Engine{Modules: mods, MaxDepth: o.depth, Workers: o.workers, Active: o.active,
		Deadline: time.Duration(o.deadline) * time.Second, Keys: loadKeys()}
	if progress {
		last := time.Now()
		e.Progress = func(msg string) {
			// at most one progress line per second keeps the UI readable
			if time.Since(last) > time.Second {
				last = time.Now()
				info("... %s", msg)
			}
		}
	}
	return e
}

func csvSet(s string) map[string]bool {
	m := map[string]bool{}
	for _, x := range strings.Split(s, ",") {
		if x = strings.TrimSpace(x); x != "" {
			m[x] = true
		}
	}
	return m
}

// scan runs the engine on one target and stores the run as a case.
func scan(target string, o scanOpts, progress bool) (*Case, Run, *Engine, error) {
	seed, err := seedFor(target)
	if err != nil {
		return nil, Run{}, nil, err
	}
	e := newEngine(o, progress)
	start := time.Now()
	fs := e.Run(seed)
	run := Run{Started: start.UTC(), Seconds: time.Since(start).Seconds(), Version: Version, Findings: fs}
	c, err := saveRun(seed.Value, seed.Type, run)
	if err != nil {
		warn("Could not save case: %v", err)
	}
	return c, run, e, nil
}

func runEngineCommand(cmd string, args []string) int {
	switch cmd {
	case "deep":
		return cmdDeep(args)
	case "watch":
		return cmdWatch(args)
	case "watchscan": // single-argument form used by the UI
		return cmdWatch(append([]string{"scan"}, args...))
	case "cases":
		for _, n := range listCases() {
			if c, err := loadCase(n); err == nil && len(c.Runs) > 0 {
				r := c.Runs[len(c.Runs)-1]
				fmt.Printf("%-40s %d runs, last %s, %d findings\n", n, len(c.Runs), r.Started.Format("2006-01-02 15:04"), len(r.Findings))
			}
		}
		return 0
	case "export":
		return cmdExport(args)
	case "modules":
		keys := loadKeys()
		for _, m := range allModules() {
			st := "free"
			if m.Key != "" {
				st = "needs " + m.Key
				if keys[m.Key] != "" {
					st = "unlocked (key)"
				}
			}
			if m.Active {
				st += ", active (--active)"
			}
			ins := []string{}
			for _, k := range m.In {
				ins = append(ins, string(k))
			}
			outs := []string{}
			for _, k := range m.Out {
				outs = append(outs, string(k))
			}
			fmt.Printf("%-15s %-28s %s -> %s\n    %s\n", m.Name, st, strings.Join(ins, ","), strings.Join(outs, ","), m.Desc)
		}
		fmt.Printf("\nKeys file: %s\n", filepath.Join(configDir(), "keys.env"))
		return 0
	case "update-data":
		return cmdUpdateData()
	}
	return 2
}

func cmdDeep(args []string) int {
	fs := flag.NewFlagSet("deep", flag.ContinueOnError)
	var o scanOpts
	o.register(fs)
	asJSON := fs.Bool("json", false, "print findings as JSON lines")
	target, rest := splitTarget(args)
	if fs.Parse(rest) != nil || target == "" {
		fmt.Fprintln(os.Stderr, "Usage: osint-cli deep <domain|host|ip|ASN|CVE> [--depth 4] [--deadline 240] [--json] [--modules a,b] [--exclude a,b] [--fresh]")
		return 2
	}
	if !*asJSON {
		head("Deep scan: %s", target)
		info("Entity engine: findings feed matching modules automatically")
	}
	c, run, e, err := scan(target, o, !*asJSON)
	if err != nil {
		warn("%v", err)
		return 1
	}
	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		for _, f := range run.Findings {
			enc.Encode(f)
		}
		return 0
	}
	renderText(c.Target, run.Findings, e, time.Duration(run.Seconds*float64(time.Second)))
	head("Case")
	info("Saved as '%s' (%d runs). Export: osint-cli export %s md", c.Name, len(c.Runs), c.Name)
	if len(c.Runs) > 1 {
		renderDiff(diffRuns(c.Runs[len(c.Runs)-2].Findings, run.Findings), c.Runs[len(c.Runs)-2].Started)
	}
	return 0
}

// splitTarget allows flags before or after the target.
func splitTarget(args []string) (string, []string) {
	var rest []string
	target := ""
	for i := 0; i < len(args); i++ {
		a := args[i]
		if strings.HasPrefix(a, "-") {
			rest = append(rest, a)
			if !strings.Contains(a, "=") && i+1 < len(args) && !isBoolFlag(a) {
				rest = append(rest, args[i+1])
				i++
			}
			continue
		}
		if target == "" {
			target = a
		}
	}
	return target, rest
}

func isBoolFlag(a string) bool {
	switch strings.TrimLeft(a, "-") {
	case "json", "active", "fresh":
		return true
	}
	return false
}

// ---------------------------------------------------------------------------
// Watch mode
// ---------------------------------------------------------------------------

func renderDiff(d Diff, since time.Time) (alerts int) {
	head("Changes since %s", since.Local().Format("2006-01-02 15:04"))
	if len(d.Added) == 0 && len(d.Removed) == 0 {
		info("No changes")
		return 0
	}
	for _, f := range d.Added {
		if f.Type == KHost || f.Type == KPort || f.Type == KLookalike || f.Type == KIssue || f.Type == KIP || f.Type == KCert {
			msg := fmt.Sprintf("NEW %s: %s", f.Type, f.Value)
			if f.Detail != "" {
				msg += "  " + shorten(f.Detail, 70)
			}
			if f.Severity >= SevMedium || f.Type == KLookalike || f.Type == KPort {
				warn("%s", msg)
				alerts++
			} else {
				found("%s", msg)
			}
		}
	}
	for _, f := range d.Removed {
		if f.Type == KHost || f.Type == KPort || f.Type == KIssue || f.Type == KIP {
			miss("GONE %s: %s", f.Type, f.Value)
		}
	}
	return alerts
}

func cmdWatch(args []string) int {
	sub := ""
	if len(args) > 0 {
		sub, args = strings.ToLower(args[0]), args[1:]
	}
	fs := flag.NewFlagSet("watch", flag.ContinueOnError)
	var o scanOpts
	o.register(fs)
	target, rest := splitTarget(args)
	if fs.Parse(rest) != nil {
		return 2
	}
	switch sub {
	case "add", "rm", "remove":
		seed, err := seedFor(target)
		if err != nil {
			warn("%v", err)
			return 1
		}
		if sub == "add" {
			ok, err := watchAdd(seed.Value)
			mustf(err, "save watch list")
			if ok {
				found("Watching %s", seed.Value)
			} else {
				info("%s is already watched", seed.Value)
			}
		} else if ok, _ := watchRemove(seed.Value); ok {
			found("No longer watching %s", seed.Value)
		}
		return 0
	case "list":
		head("Watched targets")
		for _, t := range loadWatch() {
			info("%s (since %s)", t.Target, t.Added.Format("2006-01-02"))
		}
		return 0
	case "scan":
		// one target, as used by the UI: add, scan, compare with last run
		seed, err := seedFor(target)
		if err != nil {
			warn("%v", err)
			return 1
		}
		watchAdd(seed.Value)
		return watchOne(seed.Value, o)
	case "run":
		total := 0
		ws := loadWatch()
		if len(ws) == 0 {
			info("Watch list empty. Add one: osint-cli watch add example.com")
		}
		for _, t := range ws {
			total += watchOne(t.Target, o)
		}
		if total > 0 {
			return 3 // alerts present: lets cron/systemd notify
		}
		return 0
	}
	fmt.Fprintln(os.Stderr, "Usage: osint-cli watch <add|rm|list|scan|run> [target] [scan flags]")
	return 2
}

func watchOne(target string, o scanOpts) int {
	head("Watch: %s", target)
	c, run, _, err := scan(target, o, false)
	if err != nil {
		warn("%v", err)
		return 0
	}
	s := summarize(run.Findings)
	info("Grade %s (%d/100), %d findings", s.Grade, s.Score, len(run.Findings))
	if len(c.Runs) < 2 {
		info("First run stored as baseline; the next run shows changes")
		for _, f := range s.Top {
			warn("[%s] %s", f.Severity, f.Value)
		}
		return 0
	}
	prev := c.Runs[len(c.Runs)-2]
	return renderDiff(diffRuns(prev.Findings, run.Findings), prev.Started)
}

// ---------------------------------------------------------------------------

func cmdExport(args []string) int {
	if len(args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: osint-cli export <case> <json|md|graphml|csv> [file]")
		return 2
	}
	c, err := loadCase(caseName(args[0]))
	if err != nil || len(c.Runs) == 0 {
		fmt.Fprintf(os.Stderr, "No case %q (see: osint-cli cases)\n", args[0])
		return 1
	}
	run := c.Runs[len(c.Runs)-1]
	var w io.Writer = os.Stdout
	if len(args) > 2 {
		f, err := os.Create(args[2])
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		defer f.Close()
		w = f
	}
	switch strings.ToLower(args[1]) {
	case "json":
		err = exportJSON(w, c, run)
	case "md", "markdown":
		err = exportMarkdown(w, c, run)
	case "graphml":
		err = exportGraphML(w, run)
	case "csv":
		err = exportCSV(w, run)
	default:
		err = fmt.Errorf("unknown format %q", args[1])
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

// cmdUpdateData refreshes the offline data packs.
func cmdUpdateData() int {
	dir := filepath.Join(dataDir(), "data")
	os.MkdirAll(dir, 0o700)
	packs := []struct{ name, url, file string }{
		{"Public Suffix List", "https://publicsuffix.org/list/public_suffix_list.dat", "public_suffix_list.dat"},
		{"CISA KEV catalog", kevURL, "kev.json"},
	}
	rc := 0
	for _, p := range packs {
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		code, body, err := fetch(ctx, p.url, nil)
		cancel()
		if err != nil || code != 200 || len(body) < 1000 {
			warn("%s: download failed (%v, HTTP %d)", p.name, err, code)
			rc = 1
			continue
		}
		if err := os.WriteFile(filepath.Join(dir, p.file), body, 0o600); err != nil {
			warn("%s: %v", p.name, err)
			rc = 1
			continue
		}
		found("%s: %d KB", p.name, len(body)/1024)
	}
	if b, err := json.MarshalIndent(loadTakeoverSigs(), "", " "); err == nil {
		if _, err := os.Stat(filepath.Join(dir, "takeover.json")); err != nil {
			os.WriteFile(filepath.Join(dir, "takeover.json"), b, 0o600)
			found("Takeover patterns: %d services (editable copy)", len(loadTakeoverSigs()))
		}
	}
	info("Data dir: %s", dir)
	return rc
}
