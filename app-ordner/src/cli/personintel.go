// personintel.go: Anbindung der Personenmodule über die PersonIntel-Brücke.
//
// Warum ein eigener Prozess: PersonIntel trägt die geprüfte Recherchekontrolle
// (dokumentierter Zweck, Belegstufen, Bestätigung aktiver Prüfungen, Protokoll). Diese Regeln
// werden hier nicht nachgebaut, sondern benutzt. Die Brücke ist kurzlebig - sie läuft nur
// während einer Aufgabe und hinterlässt keinen Dienst.
//
// Protokoll: zeilenweises JSON über stdin/stdout, siehe personintel/bridge.py.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// Wo die Brücke gesucht wird, in dieser Reihenfolge:
//  1. $PERSONINTEL_CMD (vollständiger Befehl, durch Leerzeichen getrennt)
//  2. personintel-cli im PATH
//  3. mitgelieferte Umgebung im Bündel: $APPDIR/usr/lib/personintel/bin/personintel-cli
//  4. python3 -m personintel.cli (falls das Modul importierbar ist)
func bridgeCommand() ([]string, string) {
	if raw := strings.TrimSpace(os.Getenv("PERSONINTEL_CMD")); raw != "" {
		return append(strings.Fields(raw), "bridge"), "PERSONINTEL_CMD"
	}
	if p, err := exec.LookPath("personintel-cli"); err == nil {
		return []string{p, "bridge"}, p
	}
	// Im Bündel mitgeliefert: reine Python-Dateien unter usr/lib/personintel, ausgeführt mit
	// dem Python des Systems. Der Pfad wird über PYTHONPATH gesetzt (siehe bundledPython).
	if appdir := os.Getenv("APPDIR"); appdir != "" {
		lib := filepath.Join(appdir, "usr", "lib", "personintel")
		if st, err := os.Stat(filepath.Join(lib, "personintel", "__init__.py")); err == nil && !st.IsDir() {
			if py := anyPython(); py != "" {
				bundledLib = lib
				return []string{py, "-m", "personintel.cli", "bridge"}, py + " + bundled PersonIntel"
			}
		}
	}
	for _, py := range []string{"python3", "python"} {
		p, err := exec.LookPath(py)
		if err != nil {
			continue
		}
		check := exec.Command(p, "-c", "import personintel")
		check.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
		if check.Run() == nil {
			return []string{p, "-m", "personintel.cli", "bridge"}, p + " -m personintel.cli"
		}
	}
	return nil, ""
}

// bundledLib ist gesetzt, wenn PersonIntel aus dem Bündel benutzt wird.
var bundledLib string

func anyPython() string {
	for _, py := range []string{"python3", "python3.12", "python3.11", "python3.10", "python"} {
		if p, err := exec.LookPath(py); err == nil {
			return p
		}
	}
	return ""
}

const bridgeRequirement = "The bundle carries PersonIntel, but no python3 was found on the device. " +
	"Install python3 (>= 3.10), or set PERSONINTEL_CMD to an existing personintel-cli."

// bridge ist eine laufende Brücke.
type bridge struct {
	cmd  *exec.Cmd
	in   *os.File
	out  *bufio.Scanner
	id   int
	path string
}

type bridgeMsg struct {
	ID          any             `json:"id"`
	OK          *bool           `json:"ok"`
	Event       string          `json:"event"`
	Error       string          `json:"error"`
	Requirement string          `json:"requirement"`
	raw         json.RawMessage // vollständige Zeile für typisierte Felder
}

func openBridge(dataDir string) (*bridge, error) {
	argv, path := bridgeCommand()
	if argv == nil {
		return nil, fmt.Errorf("PersonIntel not found")
	}
	if dataDir != "" {
		// --data-dir ist ein globales Argument und steht vor dem Unterbefehl.
		argv = append(argv[:len(argv)-1], "--data-dir", dataDir, argv[len(argv)-1])
	}
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Env = append(os.Environ(), "PYTHONUNBUFFERED=1", "PYTHONDONTWRITEBYTECODE=1")
	if bundledLib != "" {
		// Nur anhängen, damit eine auf dem Gerät installierte Fassung Vorrang behält.
		if old := os.Getenv("PYTHONPATH"); old != "" {
			cmd.Env = append(cmd.Env, "PYTHONPATH="+old+string(os.PathListSeparator)+bundledLib)
		} else {
			cmd.Env = append(cmd.Env, "PYTHONPATH="+bundledLib)
		}
	}
	stdinR, stdinW, err := os.Pipe()
	if err != nil {
		return nil, err
	}
	stdoutR, stdoutW, err := os.Pipe()
	if err != nil {
		stdinR.Close()
		stdinW.Close()
		return nil, err
	}
	cmd.Stdin = stdinR
	cmd.Stdout = stdoutW
	cmd.Stderr = os.NewFile(2, "stderr")
	if err := cmd.Start(); err != nil {
		stdinR.Close()
		stdinW.Close()
		stdoutR.Close()
		stdoutW.Close()
		return nil, err
	}
	stdinR.Close()
	stdoutW.Close()
	sc := bufio.NewScanner(stdoutR)
	sc.Buffer(make([]byte, 0, 64*1024), 8*1024*1024)
	return &bridge{cmd: cmd, in: stdinW, out: sc, path: path}, nil
}

func (b *bridge) close() {
	if b.in != nil {
		fmt.Fprintln(b.in, `{"op":"bye"}`)
		b.in.Close()
	}
	done := make(chan struct{})
	go func() { b.cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		if b.cmd.Process != nil {
			b.cmd.Process.Kill()
		}
		<-done
	}
}

// call sendet eine Anfrage und liefert alle Antwortzeilen bis zur Abschlusszeile.
// onEvent wird für jede Zwischenmeldung aufgerufen (Streaming in die Oberfläche).
func (b *bridge) call(req map[string]any, onEvent func(string, json.RawMessage)) (json.RawMessage, error) {
	b.id++
	req["id"] = b.id
	payload, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	if _, err := fmt.Fprintf(b.in, "%s\n", payload); err != nil {
		return nil, fmt.Errorf("bridge gone: %v", err)
	}
	for b.out.Scan() {
		line := b.out.Bytes()
		if len(strings.TrimSpace(string(line))) == 0 {
			continue
		}
		var m bridgeMsg
		raw := make(json.RawMessage, len(line))
		copy(raw, line)
		if err := json.Unmarshal(raw, &m); err != nil {
			continue // keine JSON-Zeile: ignorieren, nicht abbrechen
		}
		if m.Event != "" {
			if onEvent != nil {
				onEvent(m.Event, raw)
			}
			continue
		}
		if m.OK == nil {
			continue
		}
		if !*m.OK {
			msg := m.Error
			if m.Requirement != "" {
				msg += " - " + m.Requirement
			}
			return raw, fmt.Errorf("%s", msg)
		}
		return raw, nil
	}
	if err := b.out.Err(); err != nil {
		return nil, fmt.Errorf("bridge read error: %v", err)
	}
	return nil, fmt.Errorf("bridge ended without an answer")
}

// ---------------------------------------------------------------- Nutzdaten
type piStatus struct {
	Adapter     string   `json:"adapter"`
	Name        string   `json:"name"`
	Category    string   `json:"category"`
	State       string   `json:"state"`
	StateLabel  string   `json:"state_label"`
	Version     string   `json:"version"`
	Message     string   `json:"message"`
	Requirement string   `json:"requirement"`
	License     string   `json:"license"`
	Connection  string   `json:"connection"`
	Enabled     bool     `json:"enabled"`
	Kinds       []string `json:"kinds"`
	Modes       []string `json:"modes"`
	NeedsKey    bool     `json:"needs_key"`
	Cost        bool     `json:"cost"`
}

type piSource struct {
	Description string `json:"description"`
	URL         string `json:"url"`
	Kind        string `json:"kind"`
	RetrievedAt string `json:"retrieved_at"`
	ToolVersion string `json:"tool_version"`
	Active      bool   `json:"active"`
}

type piFinding struct {
	Adapter       string         `json:"adapter"`
	Name          string         `json:"name"`
	FindingID     string         `json:"finding_id"`
	Type          string         `json:"type"`
	Title         string         `json:"title"`
	Value         string         `json:"value"`
	URL           string         `json:"url"`
	Status        string         `json:"status"`
	Evidence      string         `json:"evidence"`
	EvidenceLabel string         `json:"evidence_label"`
	Review        string         `json:"review"`
	ObservedAt    string         `json:"observed_at"`
	Tags          []string       `json:"tags"`
	Source        *piSource      `json:"source"`
	Data          map[string]any `json:"data"`
}

type piCase struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	PurposeValid bool   `json:"purpose_valid"`
	Purpose      *struct {
		Category     string   `json:"category"`
		Description  string   `json:"description"`
		AuthorizedBy string   `json:"authorized_by"`
		ExpiresAt    string   `json:"expires_at"`
		ActiveOK     bool     `json:"active_checks_allowed"`
		AllowedKinds []string `json:"allowed_kinds"`
	} `json:"purpose"`
	Targets []struct {
		ID    string `json:"id"`
		Kind  string `json:"kind"`
		Value string `json:"value"`
	} `json:"targets"`
	TargetsMax int `json:"targets_max"`
	Findings   int `json:"findings"`
}

// dataDir: eigenes Verzeichnis neben der App, damit Fälle auf dem Gerät bleiben.
func piDataDir() string {
	if d := strings.TrimSpace(os.Getenv("PERSONINTEL_DATA_DIR")); d != "" {
		return d
	}
	return "" // leer = XDG-Standard von PersonIntel
}

// --------------------------------------------------------- Befehle der App

// runPIStatus zeigt den echten Betriebsstatus der zehn Personenmodule.
func runPIStatus() {
	head("Person modules (PersonIntel)")
	b, err := openBridge(piDataDir())
	if err != nil {
		warn("PersonIntel bridge not available: %v", err)
		info("%s", bridgeRequirement)
		info("The infrastructure modules (domain, IP, email, username, phone) keep working without it.")
		return
	}
	defer b.close()

	var hello struct {
		Version    string `json:"version"`
		Protocol   int    `json:"protocol"`
		Adapters   int    `json:"adapters"`
		DataDir    string `json:"data_dir"`
		Encrypted  bool   `json:"encrypted"`
		Locked     bool   `json:"credentials_locked"`
		CryptoHere bool   `json:"crypto_available"`
	}
	raw, err := b.call(map[string]any{"op": "hello"}, nil)
	if err != nil {
		warn("Bridge did not answer: %v", err)
		return
	}
	json.Unmarshal(raw, &hello)
	info("PersonIntel %s (protocol %d) via %s", hello.Version, hello.Protocol, b.path)
	info("Data: %s%s", hello.DataDir, map[bool]string{true: " (encrypted)", false: ""}[hello.Encrypted])
	if !hello.CryptoHere {
		info("No encrypted credential store on this device (the bundle is pure Python).")
		info("Pass vendor keys as PERSONINTEL_<MODULE>_<FIELD>, e.g. PERSONINTEL_PIPL_API_KEY.")
	} else if hello.Locked {
		warn("Credential store locked: modules that need an API key stay unavailable")
	}

	ready, total := 0, 0
	raw, err = b.call(map[string]any{"op": "status"}, func(ev string, line json.RawMessage) {
		if ev != "status" {
			return
		}
		var st piStatus
		if json.Unmarshal(line, &st) != nil {
			return
		}
		total++
		marker := "!"
		switch st.State {
		case "available":
			marker = "+"
			ready++
		case "disabled":
			marker = "-"
		}
		line2 := fmt.Sprintf("%s: %s", st.Name, st.StateLabel)
		if st.Version != "" {
			line2 += " (" + st.Version + ")"
		}
		emit(marker, line2)
		if len(st.Kinds) > 0 {
			info("    inputs: %s | %s", strings.Join(st.Kinds, ", "), strings.Join(st.Modes, "+"))
		}
		if st.Requirement != "" {
			info("    needs: %s", shorten(st.Requirement, 160))
		} else if st.Message != "" && st.State != "available" {
			info("    %s", shorten(st.Message, 160))
		}
		if st.Cost {
			info("    queries are charged by the vendor")
		}
	})
	if err != nil {
		warn("Status failed: %v", err)
		return
	}
	head("Summary")
	if ready == 0 {
		warn("%d of %d person modules ready", ready, total)
		info("Each module above names what it needs. Nothing is simulated.")
	} else {
		found("%d of %d person modules ready", ready, total)
	}
	_ = raw
}

// runPICase zeigt oder setzt den dokumentierten Recherchezweck.
func runPICase(purpose string) {
	b, err := openBridge(piDataDir())
	if err != nil {
		head("Case and purpose")
		warn("PersonIntel bridge not available: %v", err)
		info("%s", bridgeRequirement)
		return
	}
	defer b.close()

	if strings.TrimSpace(purpose) == "" || strings.EqualFold(purpose, "show") {
		head("Case and purpose")
		raw, err := b.call(map[string]any{"op": "case_info"}, nil)
		if err != nil {
			warn("%v", err)
			return
		}
		var resp struct {
			Case *piCase `json:"case"`
		}
		json.Unmarshal(raw, &resp)
		if resp.Case == nil {
			warn("No case yet. Document a purpose first: person queries stay blocked until then.")
			info("Open 'Case & purpose', type why you are researching and press Start.")
			return
		}
		printCase(resp.Case)
		return
	}

	head("Documenting purpose")
	raw, err := b.call(map[string]any{
		"op": "case_open", "purpose": purpose, "category": "journalism",
		"authorized_by": deviceOwner(), "active": true, "days": 1,
	}, nil)
	if err != nil {
		warn("Purpose not accepted: %v", err)
		return
	}
	var resp struct {
		Case *piCase `json:"case"`
	}
	json.Unmarshal(raw, &resp)
	if resp.Case == nil {
		warn("Bridge returned no case")
		return
	}
	found("Purpose documented, valid until %s", shorten(resp.Case.Purpose.ExpiresAt, 20))
	printCase(resp.Case)
	info("Every active check still needs its own confirmation before it runs.")
}

func deviceOwner() string {
	if v := strings.TrimSpace(os.Getenv("PERSONINTEL_AUTHORIZED_BY")); v != "" {
		return v
	}
	return "Device user (Flipper One)"
}

func printCase(c *piCase) {
	if c.PurposeValid {
		found("Case: %s", c.Name)
	} else {
		warn("Case: %s - no valid purpose, person queries are blocked", c.Name)
	}
	if c.Purpose != nil {
		info("Purpose: %s", shorten(c.Purpose.Description, 200))
		info("Responsible: %s", c.Purpose.AuthorizedBy)
		info("Valid until: %s", shorten(c.Purpose.ExpiresAt, 20))
		if c.Purpose.ActiveOK {
			info("Active checks: allowed (each one still confirmed separately)")
		} else {
			info("Active checks: not allowed by this purpose")
		}
	}
	info("Identifiers in scope: %d of %d", len(c.Targets), c.TargetsMax)
	for _, t := range c.Targets {
		emit("i", fmt.Sprintf("  %s: %s", t.Kind, t.Value))
	}
	if c.Findings > 0 {
		info("Findings stored: %d", c.Findings)
	}
}

// runPerson führt eine Personenabfrage über alle passenden Module aus und führt die
// Ergebnisse mit dem gemeinsamen Modell zusammen. confirmed muss von der Oberfläche
// kommen, die die Bestätigung beim Menschen eingeholt hat.
func runPerson(kind, value string, confirmed bool, store *Store) {
	head("Person research: %s", kind)
	b, err := openBridge(piDataDir())
	if err != nil {
		warn("PersonIntel bridge not available: %v", err)
		info("%s", bridgeRequirement)
		info("The infrastructure modules keep working without it.")
		return
	}
	defer b.close()

	raw, err := b.call(map[string]any{"op": "case_info"}, nil)
	if err != nil {
		warn("%v", err)
		return
	}
	var ci struct {
		Case *piCase `json:"case"`
	}
	json.Unmarshal(raw, &ci)
	if ci.Case == nil || !ci.Case.PurposeValid {
		warn("No valid research purpose - person queries are blocked")
		info("Open 'Case & purpose' and document why you are researching. This is required")
		info("for every query and is written to the audit log.")
		return
	}
	info("Case: %s (purpose valid until %s)", ci.Case.Name, shorten(ci.Case.Purpose.ExpiresAt, 20))

	req := map[string]any{"op": "query", "kind": kind, "value": value, "timeout": 150}
	if confirmed {
		req["confirm"] = map[string]any{
			"typed_target": value, "third_party": true, "tos": true,
			"note": "confirmed on the device (Flipper One UI)",
		}
	}

	nFind, nSkip, nDeny := 0, 0, 0
	store.Scope(kindToModelKind(kind), value)
	raw, err = b.call(req, func(ev string, line json.RawMessage) {
		switch ev {
		case "started":
			var st struct {
				Name string `json:"name"`
				Mode string `json:"mode"`
				Cost string `json:"cost"`
			}
			json.Unmarshal(line, &st)
			if st.Mode == "active" {
				info("%s: active check started (contacts third parties)", st.Name)
			} else {
				info("%s: passive check started", st.Name)
			}
			if st.Cost != "" {
				info("    %s", shorten(st.Cost, 120))
			}
		case "skipped":
			var sk struct {
				Name, Reason string
			}
			json.Unmarshal(line, &sk)
			nSkip++
			miss("%s: %s", sk.Name, shorten(sk.Reason, 150))
		case "denied":
			var dn struct {
				Name, Reason string
			}
			json.Unmarshal(line, &dn)
			nDeny++
			warn("%s: %s", dn.Name, shorten(dn.Reason, 160))
		case "finding":
			var f piFinding
			if json.Unmarshal(line, &f) != nil {
				return
			}
			nFind++
			addPersonFinding(store, f)
		case "query":
			var q struct {
				Name, State, Message string
				Findings             int
			}
			json.Unmarshal(line, &q)
			switch q.State {
			case "failed":
				warn("%s failed: %s", q.Name, shorten(q.Message, 150))
			case "cancelled":
				warn("%s cancelled", q.Name)
			default:
				info("%s: %s", q.Name, shorten(q.Message, 150))
			}
		}
	})
	if err != nil {
		warn("Query not possible: %v", err)
		return
	}
	var res struct {
		Started  []string `json:"started"`
		Skipped  []string `json:"skipped"`
		Failed   []string `json:"failed"`
		Findings int      `json:"findings"`
	}
	json.Unmarshal(raw, &res)

	head("Person modules used")
	if len(res.Started) == 0 {
		warn("No module could run this query")
		if nSkip > 0 {
			info("%d module(s) need a prerequisite - see the lines above", nSkip)
		}
		if nDeny > 0 {
			info("%d module(s) were refused by the research controls", nDeny)
		}
	} else {
		found("%d module(s) ran: %s", len(res.Started), strings.Join(res.Started, ", "))
		if len(res.Failed) > 0 {
			warn("%d failed: %s - results are incomplete", len(res.Failed), strings.Join(res.Failed, ", "))
		}
		if nSkip > 0 {
			info("%d module(s) skipped (prerequisite missing)", nSkip)
		}
		info("%d finding(s) recorded with source, timestamp and evidence level", nFind)
	}
	if nFind > 0 {
		info("A finding is a lead, not an identity. Nothing was linked automatically.")
	}
}

func kindToModelKind(kind string) string {
	switch kind {
	case "email":
		return KindEmail
	case "phone":
		return KindPhone
	case "username":
		return KindAccount
	case "name":
		return KindPerson
	case "report_file":
		return KindDoc
	}
	return KindMeta
}

// addPersonFinding überträgt einen PersonIntel-Befund in das gemeinsame Modell.
func addPersonFinding(store *Store, f piFinding) {
	ev := evidenceFromName(f.Evidence)
	src := Source{Module: f.Adapter}
	if f.Source != nil {
		src.Description = f.Source.Description
		src.URL = f.Source.URL
		src.RetrievedAt = f.Source.RetrievedAt
		src.ToolVersion = f.Source.ToolVersion
		src.Active = f.Source.Active
	}
	if src.RetrievedAt == "" {
		src.RetrievedAt = f.ObservedAt
	}

	kind, value := KindMeta, f.Value
	switch f.Type {
	case "account", "profile":
		kind = KindAccount
		// Ein Konto wird durch seine Profil-URL identifiziert, nicht durch den Benutzernamen:
		// derselbe Name auf zwei Plattformen sind zwei Konten, nicht eines.
		if f.URL != "" {
			value = f.URL
		} else if value == "" {
			value = f.Title
		}
	case "person_record":
		kind = KindPerson
		if ev > EvIndication {
			ev = EvIndication // ein Anbieterdatensatz ist nie mehr als ein Indiz
		}
	case "breach_hint", "link_hint":
		kind = KindMeta
		ev = EvUnconfirmed
	case "document":
		kind = KindDoc
	case "summary":
		// Zusammenfassungen gehören nicht in das Ergebnismodell, nur in die Anzeige.
		emit("i", fmt.Sprintf("%s: %s", f.Name, f.Title))
		return
	}
	if strings.TrimSpace(value) == "" {
		value = f.Title
	}
	rec := store.Add(Record{Kind: kind, Value: value, Title: f.Title, URL: f.URL, Evidence: ev,
		Sources: []Source{src}, Tags: f.Tags})

	line := f.Title
	if f.Value != "" && !strings.Contains(f.Title, f.Value) {
		line += ": " + f.Value
	}
	if len(rec.Sources) > 1 {
		line += fmt.Sprintf(" [also seen by %d other module(s)]", len(rec.Sources)-1)
	}
	emit(ev.Marker(), line)
	if f.URL != "" {
		info("    %s", f.URL)
	}
	if f.Source != nil {
		extra := ""
		if f.Source.ToolVersion != "" {
			extra = " " + f.Source.ToolVersion
		}
		info("    source: %s%s, %s", shorten(f.Source.Description, 90), extra, f.Source.RetrievedAt)
	}
	if containsStr(f.Tags, "username-match") {
		info("    same handle only - no proof that it is the same person")
	}
	if containsStr(f.Tags, "vendor-record") {
		info("    vendor record - not our own evidence")
	}

	// Kontrollierte Folgeabfragen: Kandidaten merken, nichts ausführen.
	if f.Data != nil {
		collectFollowUps(store, f)
	}
}

// collectFollowUps liest abgeleitete Kennungen aus den normalisierten Angaben eines Befunds.
func collectFollowUps(store *Store, f piFinding) {
	why := f.Name + ": " + shorten(f.Title, 60)
	for _, key := range []string{"emails", "phones", "usernames"} {
		list, ok := f.Data[key].([]any)
		if !ok {
			continue
		}
		kind := KindEmail
		if key == "phones" {
			kind = KindPhone
		} else if key == "usernames" {
			kind = KindAccount
		}
		for _, v := range list {
			if s, ok := v.(string); ok {
				store.Follow(kind, s, why)
			}
		}
	}
}

// runPIReport zeigt den Recherchebericht des aktuellen Falls oder schreibt ihn in eine Datei.
// value: leer/"show" = anzeigen, sonst Zielpfad.
func runPIReport(value string) {
	head("Research report")
	b, err := openBridge(piDataDir())
	if err != nil {
		warn("PersonIntel bridge not available: %v", err)
		info("%s", bridgeRequirement)
		return
	}
	defer b.close()

	if path := strings.TrimSpace(value); path != "" && !strings.EqualFold(path, "show") {
		raw, err := b.call(map[string]any{"op": "report", "format": "md", "output": path}, nil)
		if err != nil {
			warn("%v", err)
			return
		}
		var res struct {
			Written string `json:"written"`
			Bytes   int    `json:"bytes"`
		}
		json.Unmarshal(raw, &res)
		found("Written: %s (%d bytes)", res.Written, res.Bytes)
		return
	}

	n := 0
	_, err = b.call(map[string]any{"op": "report", "format": "md"}, func(ev string, line json.RawMessage) {
		if ev != "line" {
			return
		}
		var l struct {
			Text string `json:"text"`
		}
		json.Unmarshal(line, &l)
		t := strings.TrimSpace(l.Text)
		n++
		switch {
		case strings.HasPrefix(t, "#"):
			head("%s", strings.TrimLeft(t, "# "))
		case t == "":
			// Leerzeilen des Markdown überspringen: das Display ist 12 Zeilen hoch.
		default:
			emit("i", l.Text)
		}
	})
	if err != nil {
		warn("%v", err)
		return
	}
	if n == 0 {
		warn("Report is empty - no case or no findings yet")
	}
}

// runPIGraph zeigt die übernommenen Verbindungen und die Hinweise, die noch keine sind.
func runPIGraph() {
	head("Evidenced links")
	b, err := openBridge(piDataDir())
	if err != nil {
		warn("PersonIntel bridge not available: %v", err)
		info("%s", bridgeRequirement)
		return
	}
	defer b.close()

	nodes, edges := 0, 0
	_, err = b.call(map[string]any{"op": "graph_nodes"}, func(ev string, line json.RawMessage) {
		switch ev {
		case "node":
			var n struct {
				Label, Type string
				Findings    []string `json:"findings"`
			}
			json.Unmarshal(line, &n)
			nodes++
			emit("i", fmt.Sprintf("node: %s (%s, %d finding(s))", n.Label, n.Type, len(n.Findings)))
		case "edge":
			var e struct {
				Source, Target, Relation, Evidence, EvidenceLabel, Note string
				Basis                                                   []string `json:"basis"`
			}
			json.Unmarshal(line, &e)
			edges++
			ev := evidenceFromName(e.Evidence)
			emit(ev.Marker(), fmt.Sprintf("%s -> %s (%s) [%s]", e.Source, e.Target, e.Relation, e.EvidenceLabel))
			if e.Note != "" {
				info("    reason: %s", shorten(e.Note, 150))
			}
			info("    based on %d finding(s)", len(e.Basis))
		}
	})
	if err != nil {
		warn("%v", err)
		return
	}
	if edges == 0 {
		info("No links taken over yet.")
		info("Links are never created automatically: each one needs a finding as evidence")
		info("and a reason, and is entered by the researcher.")
	}

	head("Hints (not links)")
	hints := 0
	_, err = b.call(map[string]any{"op": "graph_suggest"}, func(ev string, line json.RawMessage) {
		if ev != "suggestion" {
			return
		}
		var s struct {
			Description string `json:"description"`
		}
		json.Unmarshal(line, &s)
		hints++
		emit("?", shorten(s.Description, 200))
	})
	if err != nil {
		warn("%v", err)
		return
	}
	if hints == 0 {
		info("No hints.")
	} else {
		info("A hint is a question, not a result. Same handle or same number is no proof")
		info("that two accounts belong to the same person.")
	}
}
