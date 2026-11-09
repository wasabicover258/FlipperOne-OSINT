package main

import (
	"strings"
	"testing"
)

func TestDeduplicationMergesSourcesNotAccounts(t *testing.T) {
	s := NewStore()
	// Dasselbe Profil, zwei Quellen -> ein Eintrag mit zwei Quellen.
	s.Add(Record{Kind: KindAccount, Value: "https://github.com/jdoe", Title: "GitHub",
		Evidence: EvIndication, Sources: []Source{{Module: "username", Description: "HTTP check"}}})
	s.Add(Record{Kind: KindAccount, Value: "https://github.com/jdoe/", Title: "GitHub (Sherlock)",
		Evidence: EvIndication, Sources: []Source{{Module: "sherlock", Description: "CSV"}}})
	if s.Len() != 1 {
		t.Fatalf("expected 1 merged record, got %d", s.Len())
	}
	r := s.Records()[0]
	if len(r.Sources) != 2 {
		t.Fatalf("expected 2 sources, got %d", len(r.Sources))
	}

	// Gleicher Benutzername, andere Plattform -> zwei Eintraege.
	s.Add(Record{Kind: KindAccount, Value: "https://mastodon.social/@jdoe", Title: "Mastodon",
		Evidence: EvIndication, Sources: []Source{{Module: "sherlock"}}})
	if s.Len() != 2 {
		t.Fatalf("different platforms must stay separate, got %d records", s.Len())
	}
}

func TestMergeKeepsHigherEvidenceAndNeverLowers(t *testing.T) {
	s := NewStore()
	s.Add(Record{Kind: KindEmail, Value: "a@example.org", Evidence: EvUnconfirmed,
		Sources: []Source{{Module: "pipl"}}})
	s.Add(Record{Kind: KindEmail, Value: "A@Example.org", Evidence: EvIndication,
		Sources: []Source{{Module: "holehe"}}})
	if got := s.Records()[0].Evidence; got != EvIndication {
		t.Fatalf("expected indication after merge, got %v", got)
	}
	s.Add(Record{Kind: KindEmail, Value: "a@example.org", Evidence: EvUnconfirmed,
		Sources: []Source{{Module: "spokeo"}}})
	if got := s.Records()[0].Evidence; got != EvIndication {
		t.Fatalf("a weaker source must not lower the level, got %v", got)
	}
}

func TestPhoneAndHostNormalisation(t *testing.T) {
	s := NewStore()
	s.Add(Record{Kind: KindPhone, Value: "+49 171 1234567", Evidence: EvIndication})
	s.Add(Record{Kind: KindPhone, Value: "+49-171-1234567", Evidence: EvIndication})
	s.Add(Record{Kind: KindPhone, Value: "(+49) 171 / 123 45 67", Evidence: EvIndication})
	if s.Len() != 1 {
		t.Fatalf("phone formats must merge, got %d", s.Len())
	}
	s.Add(Record{Kind: KindHost, Value: "Example.COM.", Evidence: EvIndication})
	s.Add(Record{Kind: KindHost, Value: "example.com", Evidence: EvIndication})
	if s.Len() != 2 {
		t.Fatalf("host case/trailing dot must merge, got %d", s.Len())
	}
}

func TestEdgeEvidenceIsCappedByItsEnds(t *testing.T) {
	s := NewStore()
	s.Add(Record{Kind: KindEmail, Value: "a@example.org", Evidence: EvConfirmed})
	s.Add(Record{Kind: KindHost, Value: "example.org", Evidence: EvUnconfirmed})
	s.Link(KindEmail, "a@example.org", "uses domain", KindHost, "example.org", EvConfirmed, "test")
	if len(s.edges) != 1 {
		t.Fatalf("expected 1 edge, got %d", len(s.edges))
	}
	if s.edges[0].Evidence != EvUnconfirmed {
		t.Fatalf("edge must not exceed the weaker end, got %v", s.edges[0].Evidence)
	}
}

func TestLinkNeedsBothEndsAndIsNotDuplicated(t *testing.T) {
	s := NewStore()
	s.Add(Record{Kind: KindEmail, Value: "a@example.org", Evidence: EvIndication})
	s.Link(KindEmail, "a@example.org", "uses domain", KindHost, "unbekannt.example", EvIndication, "x")
	if len(s.edges) != 0 {
		t.Fatal("a link to an unknown record must be ignored")
	}
	s.Add(Record{Kind: KindHost, Value: "example.org", Evidence: EvIndication})
	for i := 0; i < 3; i++ {
		s.Link(KindEmail, "a@example.org", "uses domain", KindHost, "example.org", EvIndication, "x")
	}
	if len(s.edges) != 1 {
		t.Fatalf("the same link must be stored once, got %d", len(s.edges))
	}
	s.Link(KindEmail, "a@example.org", "same", KindEmail, "a@example.org", EvIndication, "x")
	if len(s.edges) != 1 {
		t.Fatal("a self link must be ignored")
	}
}

func TestFollowUpsAreCandidatesNotQueries(t *testing.T) {
	s := NewStore()
	s.Scope(KindEmail, "known@example.org")
	s.Follow(KindEmail, "known@example.org", "already in scope")
	if len(s.follow) != 0 {
		t.Fatal("an identifier already in scope is no follow-up candidate")
	}
	s.Follow(KindEmail, "new@example.org", "from a vendor record")
	s.Follow(KindEmail, "NEW@example.org", "same again")
	s.Follow(KindPhone, "", "empty")
	if len(s.follow) != 1 {
		t.Fatalf("expected exactly 1 candidate, got %d", len(s.follow))
	}
	if s.follow[0].Evidence != EvUnconfirmed {
		t.Fatal("a follow-up candidate is never more than unconfirmed")
	}
}

func TestEvidenceMarkersAndNames(t *testing.T) {
	cases := []struct {
		in     string
		want   Evidence
		marker string
	}{
		{"confirmed", EvConfirmed, "="},
		{"indication", EvIndication, "~"},
		{"unconfirmed", EvUnconfirmed, "?"},
		{"etwas anderes", EvUnconfirmed, "?"},
		{"", EvUnconfirmed, "?"},
	}
	for _, c := range cases {
		got := evidenceFromName(c.in)
		if got != c.want || got.Marker() != c.marker {
			t.Errorf("%q -> %v/%s, want %v/%s", c.in, got, got.Marker(), c.want, c.marker)
		}
	}
}

func TestPersonRecordIsNeverProven(t *testing.T) {
	s := NewStore()
	// Selbst wenn ein Anbieter "confirmed" meldet: ein Anbieterdatensatz bleibt ein Indiz.
	addPersonFinding(s, piFinding{Adapter: "pipl", Name: "Pipl", Type: "person_record",
		Title: "Pipl-Treffer: Erika Beispiel", Value: "Erika Beispiel", Evidence: "confirmed",
		Tags: []string{"vendor-record"}})
	if len(s.Records()) != 1 {
		t.Fatalf("expected 1 record, got %d", len(s.Records()))
	}
	if got := s.Records()[0].Evidence; got != EvIndication {
		t.Fatalf("a vendor record must stay an indication, got %v", got)
	}
}

func TestHintTypesStayUnconfirmed(t *testing.T) {
	s := NewStore()
	for _, typ := range []string{"breach_hint", "link_hint"} {
		addPersonFinding(s, piFinding{Adapter: "mosint", Name: "Mosint", Type: typ,
			Title: "hint " + typ, Value: "v-" + typ, Evidence: "indication"})
	}
	for _, r := range s.Records() {
		if r.Evidence != EvUnconfirmed {
			t.Errorf("%s must stay unconfirmed, got %v", r.Value, r.Evidence)
		}
	}
}

func TestAccountIdentityIsTheProfileURL(t *testing.T) {
	s := NewStore()
	addPersonFinding(s, piFinding{Adapter: "sherlock", Name: "Sherlock", Type: "profile",
		Title: "GitHub", Value: "jdoe", URL: "https://github.com/jdoe", Evidence: "indication"})
	addPersonFinding(s, piFinding{Adapter: "sherlock", Name: "Sherlock", Type: "profile",
		Title: "Mastodon", Value: "jdoe", URL: "https://mastodon.social/@jdoe", Evidence: "indication"})
	if s.Len() != 2 {
		t.Fatalf("same handle on two platforms = two accounts, got %d", s.Len())
	}
}

func TestSummaryIsEmptyWithoutRecords(t *testing.T) {
	s := NewStore()
	if s.Len() != 0 || s.Count(EvIndication) != 0 {
		t.Fatal("a fresh store must be empty")
	}
	// Darf nichts ausgeben und nicht abstuerzen.
	s.PrintSummary()
	s.PrintGraph()
	s.PrintFollowUps(5)
}

func TestFollowUpCollectionFromVendorData(t *testing.T) {
	s := NewStore()
	addPersonFinding(s, piFinding{Adapter: "pipl", Name: "Pipl", Type: "person_record",
		Title: "Pipl-Treffer", Value: "Erika", Evidence: "indication",
		Data: map[string]any{
			"emails":    []any{"erika@example.org", "e.b@example.org"},
			"phones":    []any{"+4930123456"},
			"usernames": []any{"erika_b"},
			"addresses": []any{"darf nicht auftauchen"},
		}})
	if len(s.follow) != 4 {
		t.Fatalf("expected 4 follow-up candidates, got %d", len(s.follow))
	}
	kinds := map[string]int{}
	for _, f := range s.follow {
		kinds[f.Kind]++
	}
	if kinds[KindEmail] != 2 || kinds[KindPhone] != 1 || kinds[KindAccount] != 1 {
		t.Fatalf("unexpected kinds: %v", kinds)
	}
	for _, f := range s.follow {
		if strings.Contains(f.Value, "darf nicht") {
			t.Fatal("addresses must not become follow-up candidates")
		}
	}
}

func TestASCIIKeepsTextReadable(t *testing.T) {
	cases := map[string]string{
		"Profil „jdoe“ gefunden": `Profil "jdoe" gefunden`,
		"Größe – 5 €":            "Groesse - 5 EUR",
		"a\tb":                   "a  b",
		"Zeile mit NBSP":         "Zeile mit NBSP",
	}
	for in, want := range cases {
		if got := ascii(in); got != want {
			t.Errorf("ascii(%q) = %q, want %q", in, got, want)
		}
	}
	if got := ascii("\x00\x1f"); got != "??" {
		t.Errorf("control characters must become '?', got %q", got)
	}
}

func TestBridgeCommandFallsBackAndReportsSource(t *testing.T) {
	t.Setenv("PERSONINTEL_CMD", "/opt/pi/bin/personintel-cli")
	argv, src := bridgeCommand()
	if len(argv) != 2 || argv[0] != "/opt/pi/bin/personintel-cli" || argv[1] != "bridge" {
		t.Fatalf("unexpected argv: %v", argv)
	}
	if src != "PERSONINTEL_CMD" {
		t.Fatalf("unexpected source: %s", src)
	}
}

func TestKindMapping(t *testing.T) {
	want := map[string]string{"email": KindEmail, "phone": KindPhone, "username": KindAccount,
		"name": KindPerson, "report_file": KindDoc, "sonst": KindMeta}
	for in, exp := range want {
		if got := kindToModelKind(in); got != exp {
			t.Errorf("%s -> %s, want %s", in, got, exp)
		}
	}
}
