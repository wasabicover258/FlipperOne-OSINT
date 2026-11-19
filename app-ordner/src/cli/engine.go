package main

import (
	"context"
	"errors"
	"sort"
	"strings"
	"sync"
	"time"
)

// Module is one data source or check. It declares its input and output
// kinds; the engine feeds every new entity of an input kind into it.
type Module struct {
	Name    string
	Desc    string
	In      []Kind
	Out     []Kind
	Timeout time.Duration // per call; default 20s
	Rate    time.Duration // minimum gap between two calls (rate limit)
	Retries int           // extra attempts on a transient error
	Key     string        // API key name in keys.env; "" = free
	Active  bool          // touches the target directly beyond normal web/TLS use
	Run     func(ctx context.Context, in Finding, out *Out) error
}

// errPermanent marks errors that retrying cannot fix (404, bad input ...).
var errPermanent = errors.New("permanent")

// Out collects the findings of one module call.
type Out struct {
	mod    *Module
	parent Finding
	eng    *Engine
}

// Add reports a finding; parent, module, depth and time are filled in.
func (o *Out) Add(f Finding) {
	f.Module = o.mod.Name
	if f.Source == "" {
		f.Source = o.mod.Name
	}
	if f.Confidence == 0 {
		f.Confidence = 80
	}
	f.Parent = o.parent.Key()
	f.Depth = o.parent.Depth + 1
	f.Time = time.Now().UTC()
	o.eng.add(f)
}

// Engine runs modules over a growing set of entities, SpiderFoot-style.
type Engine struct {
	Modules  []*Module
	MaxDepth int           // stop recursing beyond this many hops
	Scope    []string      // domain suffixes that count as "ours"
	Workers  int           // parallel module calls
	Deadline time.Duration // soft limit for the whole run
	Active   bool          // allow Active modules
	Keys     map[string]string
	Progress func(msg string) // optional live progress output

	mu       sync.Mutex
	seen     map[string]bool
	findings []Finding
	wg       sync.WaitGroup
	sem      chan struct{}
	limiters map[string]*limiter
	ctx      context.Context
	Errors   map[string]int // module -> failed calls
	TimedOut bool
}

type limiter struct {
	mu   sync.Mutex
	next time.Time
}

func (l *limiter) wait(ctx context.Context, gap time.Duration) error {
	if gap <= 0 {
		return nil
	}
	l.mu.Lock()
	now := time.Now()
	at := l.next
	if at.Before(now) {
		at = now
	}
	l.next = at.Add(gap)
	l.mu.Unlock()
	select {
	case <-time.After(time.Until(at)):
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Enabled reports whether a module can run with the current keys/settings.
func (e *Engine) Enabled(m *Module) bool {
	if m.Key != "" && e.Keys[m.Key] == "" {
		return false
	}
	if m.Active && !e.Active {
		return false
	}
	return true
}

// Run scans from the seed and returns all findings, sorted by severity.
func (e *Engine) Run(seed Finding) []Finding {
	if e.Workers <= 0 {
		e.Workers = 8
	}
	if e.Deadline <= 0 {
		e.Deadline = 240 * time.Second
	}
	if e.MaxDepth <= 0 {
		e.MaxDepth = 4
	}
	if len(e.Scope) == 0 {
		if seed.Type == KDomain || seed.Type == KHost {
			e.Scope = []string{registrableDomain(seed.Value)}
		} else {
			// IP/ASN/CVE targets: hostnames are reported, not followed;
			// pivoting to a domain is the user's decision.
			e.Scope = []string{"\x00"}
		}
	}
	e.seen = map[string]bool{}
	e.limiters = map[string]*limiter{}
	e.Errors = map[string]int{}
	e.sem = make(chan struct{}, e.Workers)
	var cancel context.CancelFunc
	e.ctx, cancel = context.WithTimeout(context.Background(), e.Deadline)
	defer cancel()

	seed.Time = time.Now().UTC()
	if seed.Source == "" {
		seed.Source = "input"
	}
	if seed.Confidence == 0 {
		seed.Confidence = 100
	}
	e.add(seed)
	e.wg.Wait()
	if e.ctx.Err() != nil {
		e.TimedOut = true
	}

	e.mu.Lock()
	defer e.mu.Unlock()
	out := append([]Finding(nil), e.findings...)
	sortFindings(out)
	return out
}

func sortFindings(fs []Finding) {
	sort.SliceStable(fs, func(i, j int) bool {
		if fs[i].Severity != fs[j].Severity {
			return fs[i].Severity > fs[j].Severity
		}
		if fs[i].Type != fs[j].Type {
			return fs[i].Type < fs[j].Type
		}
		return fs[i].Value < fs[j].Value
	})
}

// InScope decides whether an entity may be expanded further.
func (e *Engine) InScope(f Finding) bool {
	switch f.Type {
	case KDomain, KHost:
		if len(e.Scope) == 0 {
			return true
		}
		v := strings.ToLower(strings.TrimSuffix(f.Value, "."))
		for _, s := range e.Scope {
			if v == s || strings.HasSuffix(v, "."+s) {
				return true
			}
		}
		return false
	case KASN:
		return f.Data["relation"] == "" // upstreams/peers are context, not targets
	case KLookalike, KIssue, KNetblock:
		return false // reported, never expanded (no scope creep)
	}
	return true
}

func (e *Engine) add(f Finding) {
	f.Value = strings.TrimSpace(f.Value)
	if f.Value == "" {
		return
	}
	e.mu.Lock()
	k := f.Key()
	if e.seen[k] {
		e.mu.Unlock()
		return
	}
	e.seen[k] = true
	e.findings = append(e.findings, f)
	e.mu.Unlock()

	// Depth limits pivots only; enrichment kinds (port, cve, cert ...) of an
	// accepted entity are always processed.
	if !f.IsEntity() || (f.Depth >= e.MaxDepth && isPivot(f.Type)) || !e.InScope(f) {
		return
	}
	for _, m := range e.Modules {
		if !e.Enabled(m) || !hasKind(m.In, f.Type) {
			continue
		}
		e.wg.Add(1)
		go e.call(m, f)
	}
}

func isPivot(k Kind) bool {
	switch k {
	case KDomain, KHost, KIP, KASN:
		return true
	}
	return false
}

func hasKind(ks []Kind, k Kind) bool {
	for _, x := range ks {
		if x == k {
			return true
		}
	}
	return false
}

func (e *Engine) limiterFor(name string) *limiter {
	e.mu.Lock()
	defer e.mu.Unlock()
	l := e.limiters[name]
	if l == nil {
		l = &limiter{}
		e.limiters[name] = l
	}
	return l
}

func (e *Engine) call(m *Module, in Finding) {
	defer e.wg.Done()
	select {
	case e.sem <- struct{}{}:
	case <-e.ctx.Done():
		return
	}
	defer func() { <-e.sem }()

	timeout := m.Timeout
	if timeout <= 0 {
		timeout = 20 * time.Second
	}
	out := &Out{mod: m, parent: in, eng: e}
	var err error
	for attempt := 0; attempt <= m.Retries; attempt++ {
		if attempt > 0 {
			select {
			case <-time.After(time.Duration(attempt) * 1500 * time.Millisecond):
			case <-e.ctx.Done():
				return
			}
		}
		if e.limiterFor(m.Name).wait(e.ctx, m.Rate) != nil {
			return
		}
		ctx, cancel := context.WithTimeout(e.ctx, timeout)
		err = safeRun(m, ctx, in, out)
		cancel()
		if err == nil || errors.Is(err, errPermanent) || e.ctx.Err() != nil {
			break
		}
	}
	if err != nil && !errors.Is(err, errPermanent) {
		e.mu.Lock()
		e.Errors[m.Name]++
		e.mu.Unlock()
	}
	if e.Progress != nil && err == nil {
		e.Progress(m.Name + " <- " + shorten(in.Value, 28))
	}
}

// safeRun keeps a panicking module from taking down the whole scan.
func safeRun(m *Module, ctx context.Context, in Finding, out *Out) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = errPermanent
		}
	}()
	return m.Run(ctx, in, out)
}
