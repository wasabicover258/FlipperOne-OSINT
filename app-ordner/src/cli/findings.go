// findings.go: gemeinsames Ergebnis- und Graphmodell für beide Hälften der App.
//
// Die Infrastrukturmodule (domain, ip, email, username, phone) und die Personenmodule
// (über PersonIntel) legen ihre Treffer in denselben Speicher. Jeder Eintrag nennt seine
// Quelle, den Zeitpunkt und eine Belegstufe; gleiche Treffer aus verschiedenen Quellen
// werden zu einem Eintrag mit mehreren Quellen zusammengeführt.
//
// Grundsatz: ein Treffer ist ein Hinweis, kein Identitätsnachweis. Die höchste Stufe
// (EvConfirmed) wird von keinem Modul selbst gesetzt; sie entsteht nur durch den Prüfvermerk
// eines Menschen in PersonIntel.
package main

import (
	"fmt"
	"sort"
	"strings"
	"time"
)

// Belegstufe eines Eintrags.
type Evidence int

const (
	EvUnconfirmed Evidence = iota // unbestätigt: Rohhinweis, Suchvorschlag, Anbieterangabe
	EvIndication                  // Indiz: nachvollziehbare Quelle, kein Beweis
	EvConfirmed                   // unmittelbar belegt: nur durch Prüfvermerk eines Menschen
)

func (e Evidence) Label() string {
	switch e {
	case EvConfirmed:
		return "proven"
	case EvIndication:
		return "indication"
	default:
		return "unconfirmed"
	}
}

// Marker für die Oberfläche: '=' belegt, '~' Indiz, '?' unbestätigt.
func (e Evidence) Marker() string {
	switch e {
	case EvConfirmed:
		return "="
	case EvIndication:
		return "~"
	default:
		return "?"
	}
}

func evidenceFromName(s string) Evidence {
	switch strings.ToLower(s) {
	case "confirmed", "proven":
		return EvConfirmed
	case "indication":
		return EvIndication
	default:
		return EvUnconfirmed
	}
}

// Herkunftsnachweis eines Eintrags.
type Source struct {
	Module      string // z. B. "domain", "sherlock", "pipl"
	Description string
	URL         string
	RetrievedAt string // ISO 8601, UTC
	ToolVersion string
	Active      bool // hat Dritte kontaktiert
}

// Art eines Eintrags im gemeinsamen Modell.
const (
	KindHost    = "host"     // Hostname/Subdomain
	KindIP      = "ip"       // IP-Adresse
	KindAccount = "account"  // Konto/Profil auf einer Plattform
	KindEmail   = "email"    // E-Mail-Adresse
	KindPhone   = "phone"    // Rufnummer
	KindOrg     = "org"      // Organisation/Betreiber
	KindPerson  = "person"   // Personendatensatz (nie automatisch bestätigt)
	KindDoc     = "document" // Datei/Bericht
	KindMeta    = "meta"     // Metadaten
)

// Ein Eintrag im gemeinsamen Modell.
type Record struct {
	Kind     string
	Value    string
	Title    string
	URL      string
	Evidence Evidence
	Sources  []Source
	Tags     []string
	Note     string
	first    int // Reihenfolge des ersten Auftretens (stabile Ausgabe)
}

// Kante zwischen zwei Einträgen. Entsteht nur aus einem Befund, der sie belegt.
type Edge struct {
	From     string // Schlüssel
	To       string
	Relation string
	Evidence Evidence
	Basis    string // welcher Befund belegt die Kante
}

// Store hält Einträge und Kanten eines Durchlaufs.
type Store struct {
	byKey    map[string]*Record
	order    []string
	edges    []Edge
	edgeSeen map[string]bool
	scope    map[string]bool // dokumentierter Untersuchungsumfang (registrierte Kennungen)
	follow   []Record        // Kandidaten für Folgeabfragen - nie automatisch ausgeführt
	n        int
}

func NewStore() *Store {
	return &Store{byKey: map[string]*Record{}, edgeSeen: map[string]bool{}, scope: map[string]bool{}}
}

// normKey erzeugt den Schlüssel für die Duplikaterkennung.
func normKey(kind, value string) string {
	v := strings.ToLower(strings.TrimSpace(value))
	v = strings.TrimSuffix(v, ".")
	switch kind {
	case KindHost, KindEmail, KindOrg:
		// unverändert: schon klein geschrieben
	case KindPhone:
		var b strings.Builder
		for _, r := range v {
			if r >= '0' && r <= '9' {
				b.WriteRune(r)
			} else if r == '+' && b.Len() == 0 {
				b.WriteRune(r)
			}
		}
		v = b.String()
	case KindAccount:
		v = strings.TrimPrefix(strings.TrimPrefix(v, "https://"), "http://")
		v = strings.TrimSuffix(v, "/")
	}
	return kind + "|" + v
}

// Add fügt einen Eintrag hinzu oder führt ihn mit einem vorhandenen zusammen.
// Beim Zusammenführen gilt die höhere Belegstufe und die Quellen werden ergänzt.
func (s *Store) Add(r Record) *Record {
	if strings.TrimSpace(r.Value) == "" {
		r.Value = r.Title
	}
	key := normKey(r.Kind, r.Value)
	if old, ok := s.byKey[key]; ok {
		if r.Evidence > old.Evidence {
			old.Evidence = r.Evidence
		}
		for _, src := range r.Sources {
			if !hasSource(old.Sources, src) {
				old.Sources = append(old.Sources, src)
			}
		}
		for _, t := range r.Tags {
			if !containsStr(old.Tags, t) {
				old.Tags = append(old.Tags, t)
			}
		}
		if old.URL == "" {
			old.URL = r.URL
		}
		if old.Note == "" {
			old.Note = r.Note
		}
		return old
	}
	s.n++
	r.first = s.n
	rec := &r
	s.byKey[key] = rec
	s.order = append(s.order, key)
	return rec
}

func hasSource(list []Source, s Source) bool {
	for _, x := range list {
		if x.Module == s.Module && x.Description == s.Description && x.URL == s.URL {
			return true
		}
	}
	return false
}

func containsStr(list []string, v string) bool {
	for _, x := range list {
		if x == v {
			return true
		}
	}
	return false
}

// Scope merkt eine Kennung als Teil des dokumentierten Untersuchungsumfangs.
func (s *Store) Scope(kind, value string) { s.scope[normKey(kind, value)] = true }

func (s *Store) InScope(kind, value string) bool { return s.scope[normKey(kind, value)] }

// Link verbindet zwei Einträge. Die Belegstufe der Kante kann die der Enden nicht übersteigen.
func (s *Store) Link(fromKind, fromVal, relation, toKind, toVal string, ev Evidence, basis string) {
	from, to := normKey(fromKind, fromVal), normKey(toKind, toVal)
	if from == to {
		return
	}
	a, okA := s.byKey[from]
	b, okB := s.byKey[to]
	if !okA || !okB {
		return
	}
	if ev > a.Evidence {
		ev = a.Evidence
	}
	if ev > b.Evidence {
		ev = b.Evidence
	}
	id := from + ">" + relation + ">" + to
	if s.edgeSeen[id] {
		return
	}
	s.edgeSeen[id] = true
	s.edges = append(s.edges, Edge{From: from, To: to, Relation: relation, Evidence: ev, Basis: basis})
}

// Follow merkt eine abgeleitete Kennung als Kandidat für eine Folgeabfrage.
// Ausgeführt wird nichts: der Bearbeiter entscheidet, und der Fallumfang begrenzt die Zahl.
func (s *Store) Follow(kind, value, why string) {
	if strings.TrimSpace(value) == "" || s.InScope(kind, value) {
		return
	}
	key := normKey(kind, value)
	for _, f := range s.follow {
		if normKey(f.Kind, f.Value) == key {
			return
		}
	}
	s.follow = append(s.follow, Record{Kind: kind, Value: value, Note: why, Evidence: EvUnconfirmed})
}

func (s *Store) Records() []*Record {
	out := make([]*Record, 0, len(s.order))
	for _, k := range s.order {
		out = append(out, s.byKey[k])
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Evidence != out[j].Evidence {
			return out[i].Evidence > out[j].Evidence
		}
		return out[i].first < out[j].first
	})
	return out
}

func (s *Store) Len() int { return len(s.order) }

func (s *Store) Count(ev Evidence) int {
	n := 0
	for _, r := range s.byKey {
		if r.Evidence == ev {
			n++
		}
	}
	return n
}

// label liefert die Anzeige eines Schlüssels.
func (s *Store) label(key string) string {
	if r, ok := s.byKey[key]; ok {
		if r.Value != "" {
			return r.Value
		}
		return r.Title
	}
	i := strings.Index(key, "|")
	if i >= 0 {
		return key[i+1:]
	}
	return key
}

// PrintSummary gibt die zusammengeführten Einträge nach Belegstufe aus.
func (s *Store) PrintSummary() {
	if s.Len() == 0 {
		return
	}
	head("Combined results (%d items)", s.Len())
	info("Proven %d | indication %d | unconfirmed %d",
		s.Count(EvConfirmed), s.Count(EvIndication), s.Count(EvUnconfirmed))
	for _, r := range s.Records() {
		mods := make([]string, 0, len(r.Sources))
		for _, src := range r.Sources {
			if !containsStr(mods, src.Module) {
				mods = append(mods, src.Module)
			}
		}
		line := fmt.Sprintf("%s: %s", r.Kind, r.Value)
		if r.Title != "" && r.Title != r.Value {
			line = fmt.Sprintf("%s (%s)", line, r.Title)
		}
		if len(mods) > 0 {
			line += " [" + strings.Join(mods, ", ") + "]"
		}
		if len(r.Sources) > 1 {
			line += fmt.Sprintf(" - %d sources", len(r.Sources))
		}
		emit(r.Evidence.Marker(), line)
		for _, src := range r.Sources {
			d := src.Description
			if d == "" {
				d = src.Module
			}
			ts := src.RetrievedAt
			if ts == "" {
				ts = time.Now().UTC().Format(time.RFC3339)
			}
			extra := ""
			if src.ToolVersion != "" {
				extra += " " + src.ToolVersion
			}
			if src.Active {
				extra += " (contacted third parties)"
			}
			info("    source: %s%s, %s", d, extra, ts)
		}
		if r.URL != "" {
			info("    %s", r.URL)
		}
		if r.Note != "" {
			info("    note: %s", r.Note)
		}
	}
}

// PrintGraph zeichnet die belegten Verbindungen als Textbaum.
func (s *Store) PrintGraph() {
	if len(s.edges) == 0 {
		return
	}
	head("Evidenced links (%d)", len(s.edges))
	info("A link is a documented relation, not proof of identity.")
	byFrom := map[string][]Edge{}
	froms := []string{}
	for _, e := range s.edges {
		if _, ok := byFrom[e.From]; !ok {
			froms = append(froms, e.From)
		}
		byFrom[e.From] = append(byFrom[e.From], e)
	}
	sort.Strings(froms)
	for _, from := range froms {
		emit("i", s.label(from))
		list := byFrom[from]
		for i, e := range list {
			branch := "|-"
			if i == len(list)-1 {
				branch = "`-"
			}
			line := fmt.Sprintf("  %s %s -> %s [%s]", branch, e.Relation, s.label(e.To), e.Evidence.Label())
			emit(e.Evidence.Marker(), line)
			if e.Basis != "" {
				info("       basis: %s", e.Basis)
			}
		}
	}
}

// PrintFollowUps zeigt mögliche Folgeabfragen - ohne eine davon auszuführen.
func (s *Store) PrintFollowUps(limit int) {
	if len(s.follow) == 0 {
		return
	}
	head("Possible follow-up queries (%d)", len(s.follow))
	info("Nothing is queried automatically. Each identifier has to be added to the case")
	info("and confirmed separately; the case scope limits how many are allowed.")
	for i, f := range s.follow {
		if limit > 0 && i >= limit {
			info("... and %d more", len(s.follow)-limit)
			break
		}
		emit("?", fmt.Sprintf("%s: %s", f.Kind, f.Value))
		if f.Note != "" {
			info("    from: %s", f.Note)
		}
	}
}
