package main

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// Local storage. Plain JSON files instead of SQLite: the Go standard library
// has no SQLite driver, a pure-Go one would roughly triple the binary size
// on the Flipper, and the data volume (a few hundred findings per case) does
// not need a database. Layout:
//
//	~/.config/flipperone-osint/keys.env     API keys (KEY=value)
//	~/.local/share/flipperone-osint/cases/  one JSON file per target, last runs
//	~/.local/share/flipperone-osint/watch.json  monitored targets
//	~/.local/share/flipperone-osint/data/   offline data packs (update-data)
//	~/.cache/flipperone-osint/http/         response cache

func homeDir() string {
	if h, err := os.UserHomeDir(); err == nil {
		return h
	}
	return "/tmp"
}

func xdg(env, fallback string) string {
	if v := os.Getenv(env); v != "" {
		return filepath.Join(v, "flipperone-osint")
	}
	return filepath.Join(homeDir(), fallback, "flipperone-osint")
}

func configDir() string { return xdg("XDG_CONFIG_HOME", ".config") }
func dataDir() string   { return xdg("XDG_DATA_HOME", ".local/share") }
func cacheDir() string  { return filepath.Join(xdg("XDG_CACHE_HOME", ".cache"), "http") }

// ---------------------------------------------------------------------------
// API keys
// ---------------------------------------------------------------------------

// loadKeys reads keys.env (and the older ai.env); real environment
// variables win. Without any key every free module still runs.
func loadKeys() map[string]string {
	keys := map[string]string{}
	for _, f := range []string{"ai.env", "keys.env"} {
		parseEnvFile(filepath.Join(configDir(), f), keys)
	}
	for _, m := range allModules() {
		if m.Key != "" {
			if v := os.Getenv(m.Key); v != "" {
				keys[m.Key] = v
			}
		}
	}
	return keys
}

func parseEnvFile(path string, into map[string]string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || line[0] == '#' {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		v = strings.Trim(strings.TrimSpace(v), `"'`)
		if v != "" {
			into[strings.TrimSpace(k)] = v
		}
	}
}

// ---------------------------------------------------------------------------
// Cases: every engine run is stored, so runs can be compared (watch mode)
// and exported later.
// ---------------------------------------------------------------------------

type Run struct {
	Started  time.Time `json:"started"`
	Seconds  float64   `json:"seconds"`
	Version  string    `json:"version"`
	Findings []Finding `json:"findings"`
}

type Case struct {
	Name   string `json:"name"`
	Target string `json:"target"`
	Kind   Kind   `json:"kind"`
	Runs   []Run  `json:"runs"` // oldest first
}

const keepRuns = 10

var slugRe = regexp.MustCompile(`[^a-z0-9._-]+`)

func caseName(target string) string {
	s := slugRe.ReplaceAllString(strings.ToLower(target), "_")
	if len(s) > 80 {
		s = s[:80]
	}
	return s
}

func casePath(name string) string { return filepath.Join(dataDir(), "cases", name+".json") }

func loadCase(name string) (*Case, error) {
	b, err := os.ReadFile(casePath(name))
	if err != nil {
		return nil, err
	}
	var c Case
	if err := json.Unmarshal(b, &c); err != nil {
		return nil, err
	}
	return &c, nil
}

// saveRun appends a run to the target's case and returns the case.
func saveRun(target string, kind Kind, run Run) (*Case, error) {
	name := caseName(target)
	c, err := loadCase(name)
	if err != nil {
		c = &Case{Name: name, Target: target, Kind: kind}
	}
	c.Runs = append(c.Runs, run)
	if len(c.Runs) > keepRuns {
		c.Runs = c.Runs[len(c.Runs)-keepRuns:]
	}
	b, err := json.MarshalIndent(c, "", " ")
	if err != nil {
		return c, err
	}
	if err := os.MkdirAll(filepath.Dir(casePath(name)), 0o700); err != nil {
		return c, err
	}
	return c, os.WriteFile(casePath(name), b, 0o600)
}

func listCases() []string {
	m, _ := filepath.Glob(filepath.Join(dataDir(), "cases", "*.json"))
	var out []string
	for _, p := range m {
		out = append(out, strings.TrimSuffix(filepath.Base(p), ".json"))
	}
	sort.Strings(out)
	return out
}

// ---------------------------------------------------------------------------
// Diff between two runs
// ---------------------------------------------------------------------------

type Diff struct {
	Added   []Finding
	Removed []Finding
}

// diffRuns compares entity/issue keys. Volatile kinds that only describe
// the scan itself are ignored.
func diffRuns(old, cur []Finding) Diff {
	idx := func(fs []Finding) map[string]Finding {
		m := map[string]Finding{}
		for _, f := range fs {
			if f.Depth == 0 {
				continue
			}
			m[f.Key()] = f
		}
		return m
	}
	o, c := idx(old), idx(cur)
	var d Diff
	for k, f := range c {
		if _, ok := o[k]; !ok {
			d.Added = append(d.Added, f)
		}
	}
	for k, f := range o {
		if _, ok := c[k]; !ok {
			d.Removed = append(d.Removed, f)
		}
	}
	sortFindings(d.Added)
	sortFindings(d.Removed)
	return d
}

// ---------------------------------------------------------------------------
// Watch list
// ---------------------------------------------------------------------------

type WatchTarget struct {
	Target string    `json:"target"`
	Added  time.Time `json:"added"`
}

func watchPath() string { return filepath.Join(dataDir(), "watch.json") }

func loadWatch() []WatchTarget {
	var w []WatchTarget
	if b, err := os.ReadFile(watchPath()); err == nil {
		json.Unmarshal(b, &w)
	}
	return w
}

func saveWatch(w []WatchTarget) error {
	b, _ := json.MarshalIndent(w, "", " ")
	if err := os.MkdirAll(dataDir(), 0o700); err != nil {
		return err
	}
	return os.WriteFile(watchPath(), b, 0o600)
}

func watchAdd(target string) (bool, error) {
	w := loadWatch()
	for _, t := range w {
		if strings.EqualFold(t.Target, target) {
			return false, nil
		}
	}
	w = append(w, WatchTarget{Target: target, Added: time.Now().UTC()})
	return true, saveWatch(w)
}

func watchRemove(target string) (bool, error) {
	w := loadWatch()
	for i, t := range w {
		if strings.EqualFold(t.Target, target) {
			w = append(w[:i], w[i+1:]...)
			return true, saveWatch(w)
		}
	}
	return false, nil
}

func mustf(err error, what string) {
	if err != nil {
		warn("%s failed: %v", what, err)
	}
}
