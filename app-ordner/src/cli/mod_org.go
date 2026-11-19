package main

// Organisations (ported from the 2.0.x GLEIF/Wikidata code into engine
// modules): organisation -> LEI records (GLEIF), LEI -> legal entity and
// parent companies, LEI/organisation -> official website domains
// (Wikidata P856). Only legal entities; no officers, employees or owners.

import (
	"context"
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"time"
)

var leiRe = regexp.MustCompile(`^[A-Z0-9]{18}[0-9]{2}$`)

// validLEI checks format and the ISO 17442 / ISO 7064 MOD 97-10 check digits.
func validLEI(s string) bool {
	if !leiRe.MatchString(s) {
		return false
	}
	rem := 0
	for _, c := range s {
		v := int(c - '0')
		if c >= 'A' {
			v = int(c-'A') + 10
		}
		if v >= 10 {
			rem = (rem*100 + v) % 97
		} else {
			rem = (rem*10 + v) % 97
		}
	}
	return rem == 1
}

// appUA identifies the app where the provider's usage policy asks for it
// (Nominatim, Wikimedia, GLEIF).
func appUA() map[string]string {
	return map[string]string{"User-Agent": "FlipperOne-OSINT/" + Version + " (+https://github.com/wasabicover258/FlipperOne-OSINT)",
		"Accept": "application/json"}
}

type gleifAddress struct {
	Lines   []string `json:"addressLines"`
	City    string   `json:"city"`
	Region  string   `json:"region"`
	Country string   `json:"country"`
	Postal  string   `json:"postalCode"`
}

func (a gleifAddress) String() string {
	return strings.Join(filterEmpty(strings.Join(a.Lines, " "), strings.TrimSpace(a.Postal+" "+a.City), a.Country), ", ")
}

type gleifRecord struct {
	ID         string `json:"id"`
	Attributes struct {
		LEI    string `json:"lei"`
		Entity struct {
			LegalName struct {
				Name string `json:"name"`
			} `json:"legalName"`
			Status       string       `json:"status"`
			Jurisdiction string       `json:"jurisdiction"`
			Category     string       `json:"category"`
			LegalAddress gleifAddress `json:"legalAddress"`
			HQAddress    gleifAddress `json:"headquartersAddress"`
		} `json:"entity"`
		Registration struct {
			Status string `json:"status"`
		} `json:"registration"`
		BIC []string `json:"bic"`
	} `json:"attributes"`
}

func (r gleifRecord) lei() string {
	id := strings.ToUpper(strings.TrimSpace(r.Attributes.LEI))
	if id == "" {
		id = strings.ToUpper(strings.TrimSpace(r.ID))
	}
	return id
}

const gleifAPI = "https://api.gleif.org/api/v1/lei-records"

// leiFinding turns a GLEIF record into a KLEI finding with the legal data.
func leiFinding(r gleifRecord, conf int, relation string) (Finding, bool) {
	id := r.lei()
	name := strings.TrimSpace(r.Attributes.Entity.LegalName.Name)
	if !leiRe.MatchString(id) || name == "" {
		return Finding{}, false
	}
	e := r.Attributes.Entity
	data := map[string]string{"name": name, "status": e.Status, "registration": r.Attributes.Registration.Status,
		"jurisdiction": e.Jurisdiction, "legal_address": e.LegalAddress.String(), "hq_address": e.HQAddress.String(),
		"url": "https://search.gleif.org/#/record/" + id}
	if len(r.Attributes.BIC) > 0 {
		data["bic"] = strings.Join(r.Attributes.BIC, " ")
	}
	if relation != "" {
		data["relation"] = relation
	}
	for k, v := range data {
		if v == "" {
			delete(data, k)
		}
	}
	d := name
	if relation != "" {
		d = relation + ": " + name
	}
	if c := strings.Join(filterEmpty(e.LegalAddress.City, e.LegalAddress.Country), ", "); c != "" {
		d += " (" + c + ")"
	}
	if e.Status != "" && e.Status != "ACTIVE" {
		d += " [" + strings.ToLower(e.Status) + "]"
	}
	return Finding{Type: KLEI, Value: id, Source: "gleif", Confidence: conf, Detail: d, Data: data}, true
}

var modGLEIF = &Module{
	Name: "gleif", Desc: "GLEIF: organisation -> LEI, LEI -> legal entity + parents",
	In: []Kind{KOrg, KLEI}, Out: []Kind{KLEI, KOrg, KAttr}, Timeout: 20 * time.Second, Retries: 1, Rate: 300 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if in.Type == KOrg {
			name := strings.TrimSpace(in.Value)
			if len(name) < 3 || len(name) > 120 {
				return fmt.Errorf("%w: name length", errPermanent)
			}
			var res struct {
				Data []gleifRecord `json:"data"`
			}
			q := url.Values{"filter[entity.legalName]": {name}, "page[size]": {"5"}}
			if err := getJSON(ctx, gleifAPI+"?"+q.Encode(), appUA(), 7*day, &res); err != nil {
				return err
			}
			exact := len(res.Data) > 0
			if !exact { // no exact legal name: full-text candidates
				q = url.Values{"filter[fulltext]": {name}, "page[size]": {"5"}}
				if err := getJSON(ctx, gleifAPI+"?"+q.Encode(), appUA(), 7*day, &res); err != nil {
					return err
				}
			}
			for _, r := range res.Data {
				conf := 50
				if exact || strings.EqualFold(strings.TrimSpace(r.Attributes.Entity.LegalName.Name), name) {
					conf = 90
				}
				if f, ok := leiFinding(r, conf, ""); ok {
					f.Data["searched"] = "yes" // record already complete
					out.Add(f)
				}
			}
			return nil
		}

		lei := strings.ToUpper(in.Value)
		if in.Data["searched"] == "" { // direct LEI input: fetch the record
			var one struct {
				Data gleifRecord `json:"data"`
			}
			if err := getJSON(ctx, gleifAPI+"/"+lei, appUA(), 7*day, &one); err != nil {
				return err
			}
			if one.Data.lei() != lei { // never accept a different record
				return fmt.Errorf("%w: LEI mismatch", errPermanent)
			}
			if f, ok := leiFinding(one.Data, 100, ""); ok {
				out.Add(Finding{Type: KOrg, Value: f.Data["name"], Source: "gleif", Confidence: 100,
					Detail: "legal name of " + lei, Data: map[string]string{"relation": "legal name"}})
				for _, k := range []string{"legal_address", "hq_address", "jurisdiction", "status", "bic"} {
					if v := f.Data[k]; v != "" {
						out.Add(Finding{Type: KAttr, Value: strings.ReplaceAll(k, "_", " ") + ": " + v, Source: "gleif", Confidence: 100})
					}
				}
			}
		}
		for _, rel := range []struct{ path, label string }{{"direct-parent", "direct parent"}, {"ultimate-parent", "ultimate parent"}} {
			var p struct {
				Data gleifRecord `json:"data"`
			}
			// 404 = no parent reported (or an exception filed): not an error.
			if getJSON(ctx, gleifAPI+"/"+lei+"/"+rel.path, appUA(), 7*day, &p) == nil && p.Data.lei() != lei {
				if f, ok := leiFinding(p.Data, 95, rel.label); ok {
					out.Add(f)
				}
			}
		}
		return nil
	},
}

// ---------------------------------------------------------------------------
// Wikidata: official websites (P856) of a legal entity.
// ---------------------------------------------------------------------------

const wikidataAPI = "https://www.wikidata.org/w/api.php?"

type wdClaims map[string][]struct {
	Mainsnak struct {
		Datavalue struct {
			Value any `json:"value"`
		} `json:"datavalue"`
	} `json:"mainsnak"`
}

func (c wdClaims) strings(prop string) []string {
	var out []string
	for _, s := range c[prop] {
		if v, ok := s.Mainsnak.Datavalue.Value.(string); ok && v != "" {
			out = append(out, v)
		}
	}
	return out
}

// websiteDomain reduces an official website URL to its registrable domain.
func websiteDomain(raw string) (string, bool) {
	if !strings.Contains(raw, "://") {
		raw = "https://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") {
		return "", false
	}
	h := strings.ToLower(strings.TrimSuffix(u.Hostname(), "."))
	if canonicalIP(h) != "" || !domainRe.MatchString(h) {
		return "", false
	}
	d := registrableDomain(h)
	return d, d != ""
}

var wdIDRe = regexp.MustCompile(`^Q[0-9]{1,12}$`)

var modWikidataOrg = &Module{
	Name: "wikidata", Desc: "Wikidata: LEI/organisation -> official website domains",
	In: []Kind{KLEI, KOrg}, Out: []Kind{KDomain, KURL, KLEI}, Timeout: 20 * time.Second, Retries: 1, Rate: 300 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var ids []string
		conf := 90
		if in.Type == KLEI {
			var s struct {
				Query struct {
					Search []struct {
						Title string `json:"title"`
					} `json:"search"`
				} `json:"query"`
			}
			q := url.Values{"action": {"query"}, "list": {"search"}, "srsearch": {"haswbstatement:P1278=" + strings.ToUpper(in.Value)},
				"srlimit": {"2"}, "format": {"json"}}
			if err := getJSON(ctx, wikidataAPI+q.Encode(), appUA(), 7*day, &s); err != nil {
				return err
			}
			for _, r := range s.Query.Search {
				ids = append(ids, r.Title)
			}
		} else {
			conf = 55 // a name match is a candidate, not an identification
			var s struct {
				Search []struct {
					ID string `json:"id"`
				} `json:"search"`
			}
			q := url.Values{"action": {"wbsearchentities"}, "search": {in.Value}, "language": {"en"}, "type": {"item"},
				"limit": {"3"}, "format": {"json"}}
			if err := getJSON(ctx, wikidataAPI+q.Encode(), appUA(), 7*day, &s); err != nil {
				return err
			}
			for _, r := range s.Search {
				ids = append(ids, r.ID)
			}
		}
		var ok []string
		for _, id := range ids {
			if wdIDRe.MatchString(id) {
				ok = append(ok, id)
			}
		}
		if len(ok) == 0 {
			return nil
		}
		var ents struct {
			Entities map[string]struct {
				Labels map[string]struct {
					Value string `json:"value"`
				} `json:"labels"`
				Claims wdClaims `json:"claims"`
			} `json:"entities"`
		}
		q := url.Values{"action": {"wbgetentities"}, "ids": {strings.Join(ok, "|")}, "props": {"claims|labels"},
			"languages": {"en"}, "format": {"json"}}
		if err := getJSON(ctx, wikidataAPI+q.Encode(), appUA(), 7*day, &ents); err != nil {
			return err
		}
		for _, id := range ok {
			e, found := ents.Entities[id]
			if !found {
				continue
			}
			label := e.Labels["en"].Value
			if label == "" {
				label = id
			}
			link := "https://www.wikidata.org/wiki/" + id
			sites := e.Claims.strings("P856")
			if in.Type == KOrg && len(sites) == 0 && len(e.Claims.strings("P1278")) == 0 {
				continue // likely not an organisation (person, place, film ...)
			}
			out.Add(Finding{Type: KURL, Value: link, Source: "wikidata", Confidence: conf, Detail: "Wikidata: " + label})
			for _, site := range sites {
				if d, ok := websiteDomain(site); ok {
					out.Add(Finding{Type: KDomain, Value: d, Source: "wikidata", Confidence: conf,
						Detail: "official website of " + label + " (" + site + ")",
						Data:   map[string]string{"relation": "official website", "url": site, "wikidata": id}})
				}
			}
			if in.Type == KOrg {
				for _, l := range e.Claims.strings("P1278") {
					if l = strings.ToUpper(l); validLEI(l) {
						out.Add(Finding{Type: KLEI, Value: l, Source: "wikidata", Confidence: conf, Detail: "LEI of " + label})
					}
				}
			}
		}
		return nil
	},
}
