package main

import (
	"encoding/csv"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Attack surface summary
// ---------------------------------------------------------------------------

type Summary struct {
	Counts [5]int // by severity
	Score  int    // 0..100
	Grade  string
	Top    []Finding // most severe issues
}

func summarize(fs []Finding) Summary {
	var s Summary
	penalty := 0
	for _, f := range fs {
		if f.Type != KIssue && f.Type != KLookalike {
			continue
		}
		s.Counts[f.Severity]++
		penalty += [...]int{0, 1, 5, 15, 40}[f.Severity]
		if f.Severity >= SevMedium && len(s.Top) < 10 {
			s.Top = append(s.Top, f)
		}
	}
	s.Score = 100 - penalty
	if s.Score < 0 {
		s.Score = 0
	}
	switch {
	case s.Score >= 90:
		s.Grade = "A"
	case s.Score >= 75:
		s.Grade = "B"
	case s.Score >= 60:
		s.Grade = "C"
	case s.Score >= 40:
		s.Grade = "D"
	default:
		s.Grade = "F"
	}
	return s
}

// ---------------------------------------------------------------------------
// Pivot suggestions: entities that connect to many others are the best next
// targets ("this IP hosts 29 other domains - follow?").
// ---------------------------------------------------------------------------

type Pivot struct {
	Entity Finding
	Links  int
	Hint   string
}

func pivots(fs []Finding) []Pivot {
	children := map[string]int{}
	for _, f := range fs {
		if f.Parent != "" {
			children[f.Parent]++
		}
	}
	var ps []Pivot
	for _, f := range fs {
		if f.Depth == 0 {
			continue
		}
		n := children[f.Key()]
		switch f.Type {
		case KIP:
			if n >= 3 {
				ps = append(ps, Pivot{f, n, fmt.Sprintf("IP links to %d entities (shared hosting?) - deep %s", n, f.Value)})
			}
		case KASN:
			if f.Data["relation"] == "" {
				ps = append(ps, Pivot{f, n, fmt.Sprintf("operator %s %s - deep %s", f.Value, shorten(f.Data["holder"], 24), f.Value)})
			}
		case KLookalike:
			if f.Severity >= SevMedium {
				ps = append(ps, Pivot{f, n, "lookalike with infrastructure - deep " + f.Value})
			}
		}
	}
	sort.SliceStable(ps, func(i, j int) bool { return ps[i].Links > ps[j].Links })
	if len(ps) > 8 {
		ps = ps[:8]
	}
	return ps
}

// ---------------------------------------------------------------------------
// Text rendering for the Flipper UI (marker lines, '#' = section)
// ---------------------------------------------------------------------------

var kindLabel = []struct {
	k     Kind
	label string
}{
	{KLookalike, "Lookalike domains"}, {KDomain, "Domains"}, {KHost, "Hostnames"}, {KIP, "IP addresses"},
	{KASN, "Networks (ASN)"}, {KNetblock, "Netblocks"}, {KPort, "Open ports"}, {KCPE, "Software (CPE)"},
	{KCVE, "CVEs (raw)"}, {KCert, "Certificates"}, {KURL, "URLs"}, {KTech, "Technologies"},
}

func marker(f Finding) func(string, ...any) {
	switch {
	case f.Severity >= SevMedium:
		return warn
	case f.Type == KIssue:
		return info
	}
	return found
}

func renderText(target string, fs []Finding, eng *Engine, elapsed time.Duration) {
	s := summarize(fs)
	head("Attack surface: %s", target)
	if len(fs) <= 1 && eng != nil && len(eng.Errors) > 0 {
		warn("No results: all sources failed - is the network reachable?")
		renderErrors(eng)
		return
	}
	info("Grade %s (%d/100)  crit %d  high %d  med %d  low %d", s.Grade, s.Score,
		s.Counts[SevCritical], s.Counts[SevHigh], s.Counts[SevMedium], s.Counts[SevLow])
	info("%d findings in %.0fs", len(fs), elapsed.Seconds())
	if eng != nil && eng.TimedOut {
		warn("Deadline reached - results are partial (--deadline)")
	}
	if len(s.Top) == 0 {
		found("No medium-or-worse issues found")
	}
	for _, f := range s.Top {
		v := f.Value
		if f.Type == KLookalike {
			v = "Lookalike domain: " + v
		}
		warn("[%s] %s", strings.ToUpper(f.Severity.String()[:4]), v)
	}

	if ps := pivots(fs); len(ps) > 0 {
		head("Pivot suggestions")
		for _, p := range ps {
			info("%s", p.Hint)
		}
	}

	var issues []Finding
	for _, f := range fs {
		if f.Type == KIssue {
			issues = append(issues, f)
		}
	}
	if len(issues) > 0 {
		head("Issues (%d)", len(issues))
		for _, f := range issues {
			marker(f)("[%s] %s", f.Severity, f.Value)
			if f.Detail != "" {
				info("  %s", shorten(f.Detail, 120))
			}
		}
	}

	for _, kl := range kindLabel {
		var sel []Finding
		for _, f := range fs {
			if f.Type == kl.k && f.Depth > 0 {
				sel = append(sel, f)
			}
		}
		if len(sel) == 0 {
			continue
		}
		head("%s (%d)", kl.label, len(sel))
		for i, f := range sel {
			if i >= 300 {
				info("... %d more (export the case for all)", len(sel)-i)
				break
			}
			line := f.Value
			if f.Detail != "" {
				line += "  " + f.Detail
			}
			marker(f)("%s  [%s]", shorten(line, 110), f.Source)
		}
	}

	renderErrors(eng)
}

func renderErrors(eng *Engine) {
	if eng != nil && len(eng.Errors) > 0 {
		head("Module errors")
		var names []string
		for n, c := range eng.Errors {
			names = append(names, fmt.Sprintf("%s(%d)", n, c))
		}
		sort.Strings(names)
		warn("Failed calls: %s", strings.Join(names, ", "))
	}
}

// ---------------------------------------------------------------------------
// Export: JSON, Markdown, GraphML (Maltego/Gephi), CSV
// ---------------------------------------------------------------------------

func exportJSON(w io.Writer, c *Case, run Run) error {
	enc := json.NewEncoder(w)
	enc.SetIndent("", " ")
	return enc.Encode(struct {
		Target string `json:"target"`
		Run
		Summary map[string]any `json:"summary"`
	}{c.Target, run, summaryMap(summarize(run.Findings))})
}

func summaryMap(s Summary) map[string]any {
	return map[string]any{"grade": s.Grade, "score": s.Score, "critical": s.Counts[4], "high": s.Counts[3], "medium": s.Counts[2], "low": s.Counts[1]}
}

func exportCSV(w io.Writer, run Run) error {
	cw := csv.NewWriter(w)
	cw.Write([]string{"type", "value", "severity", "confidence", "source", "module", "parent", "depth", "time", "detail"})
	for _, f := range run.Findings {
		cw.Write([]string{string(f.Type), f.Value, f.Severity.String(), fmt.Sprint(f.Confidence), f.Source, f.Module,
			f.Parent, fmt.Sprint(f.Depth), f.Time.Format(time.RFC3339), f.Detail})
	}
	cw.Flush()
	return cw.Error()
}

func exportMarkdown(w io.Writer, c *Case, run Run) error {
	s := summarize(run.Findings)
	fmt.Fprintf(w, "# OSINT report: %s\n\n", c.Target)
	fmt.Fprintf(w, "Scan %s, %.0f s, FlipperOne-OSINT %s\n\n", run.Started.Format("2006-01-02 15:04 MST"), run.Seconds, run.Version)
	fmt.Fprintf(w, "**Grade %s (%d/100)** - critical %d, high %d, medium %d, low %d\n\n", s.Grade, s.Score, s.Counts[4], s.Counts[3], s.Counts[2], s.Counts[1])
	fmt.Fprintf(w, "## Issues\n\n| Severity | Finding | Detail |\n|---|---|---|\n")
	for _, f := range run.Findings {
		if f.Type == KIssue || (f.Type == KLookalike && f.Severity >= SevMedium) {
			fmt.Fprintf(w, "| %s | %s | %s |\n", f.Severity, mdEsc(f.Value), mdEsc(f.Detail))
		}
	}
	for _, kl := range kindLabel {
		first := true
		for _, f := range run.Findings {
			if f.Type != kl.k || f.Depth == 0 {
				continue
			}
			if first {
				fmt.Fprintf(w, "\n## %s\n\n", kl.label)
				first = false
			}
			fmt.Fprintf(w, "- `%s` %s _(%s)_\n", f.Value, mdEsc(f.Detail), f.Source)
		}
	}
	return nil
}

func mdEsc(s string) string { return strings.NewReplacer("|", "\\|", "\n", " ").Replace(s) }

type gmlKey struct {
	ID   string `xml:"id,attr"`
	For  string `xml:"for,attr"`
	Name string `xml:"attr.name,attr"`
	Type string `xml:"attr.type,attr"`
}
type gmlData struct {
	Key string `xml:"key,attr"`
	Val string `xml:",chardata"`
}
type gmlNode struct {
	ID   string    `xml:"id,attr"`
	Data []gmlData `xml:"data"`
}
type gmlEdge struct {
	Source string `xml:"source,attr"`
	Target string `xml:"target,attr"`
}
type graphML struct {
	XMLName xml.Name `xml:"graphml"`
	NS      string   `xml:"xmlns,attr"`
	Keys    []gmlKey `xml:"key"`
	Graph   struct {
		ID          string    `xml:"id,attr"`
		EdgeDefault string    `xml:"edgedefault,attr"`
		Nodes       []gmlNode `xml:"node"`
		Edges       []gmlEdge `xml:"edge"`
	} `xml:"graph"`
}

// exportGraphML writes the entity graph (parent -> child) for Gephi,
// yEd or a Maltego import.
func exportGraphML(w io.Writer, run Run) error {
	g := graphML{NS: "http://graphml.graphdrawing.org/xmlns"}
	for _, k := range []string{"type", "value", "severity", "source", "detail"} {
		g.Keys = append(g.Keys, gmlKey{ID: k, For: "node", Name: k, Type: "string"})
	}
	g.Graph.ID = "osint"
	g.Graph.EdgeDefault = "directed"
	ids := map[string]bool{}
	for _, f := range run.Findings {
		ids[f.Key()] = true
		g.Graph.Nodes = append(g.Graph.Nodes, gmlNode{ID: f.Key(), Data: []gmlData{
			{"type", string(f.Type)}, {"value", f.Value}, {"severity", f.Severity.String()}, {"source", f.Source}, {"detail", f.Detail}}})
	}
	for _, f := range run.Findings {
		if f.Parent != "" && ids[f.Parent] {
			g.Graph.Edges = append(g.Graph.Edges, gmlEdge{f.Parent, f.Key()})
		}
	}
	io.WriteString(w, xml.Header)
	enc := xml.NewEncoder(w)
	enc.Indent("", " ")
	return enc.Encode(g)
}
