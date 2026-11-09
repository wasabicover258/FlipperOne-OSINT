package main

// publicname.go: fast, passive, source-based lookup of publicly documented
// figures via Wikidata. No PersonIntel case or credentials are required.
// Results are candidates, not assertions that similarly named people match.

import (
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "regexp"
    "strings"
)

const wikidataAPI = "https://www.wikidata.org/w/api.php"

var entityID = regexp.MustCompile("^Q[1-9][0-9]*$")

type publicProfile struct {
    Network string
    URL string
}

type publicPerson struct {
    ID string
    Name string
    Description string
    Profiles []publicProfile
}

type wikiSearch struct {
    Search []struct {
        ID string `json:"id"`
        Label string `json:"label"`
        Description string `json:"description"`
    } `json:"search"`
}

type wikiEntityResponse struct {
    Entities map[string]struct {
        Claims map[string][]struct {
            Mainsnak struct {
                Datavalue struct { Value json.RawMessage `json:"value"` } `json:"datavalue"`
            } `json:"mainsnak"`
        } `json:"claims"`
    } `json:"entities"`
}

func wikiFetch(client *http.Client, base string, values url.Values, dest any) error {
    endpoint, err := url.Parse(base)
    if err != nil || endpoint.Scheme == "" { return errors.New("invalid Wikidata API URL") }
    endpoint.RawQuery = values.Encode()
    req, err := http.NewRequest(http.MethodGet, endpoint.String(), nil)
    if err != nil { return err }
    req.Header.Set("User-Agent", "FlipperOne-OSINT/1.2 (public profiles; https://github.com/wasabicover258/FlipperOne-OSINT)")
    req.Header.Set("Accept", "application/json")
    resp, err := client.Do(req)
    if err != nil { return err }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return fmt.Errorf("Wikidata HTTP %d", resp.StatusCode)
    }
    raw, err := io.ReadAll(io.LimitReader(resp.Body, 4*1024*1024+1))
    if err != nil { return err }
    if len(raw) > 4*1024*1024 { return errors.New("Wikidata response too large") }
    if err := json.Unmarshal(raw, dest); err != nil { return fmt.Errorf("invalid Wikidata JSON: %w", err) }
    return nil
}

func claimText(raw json.RawMessage) string {
    var val string
    if err := json.Unmarshal(raw, &val); err != nil { return "" }
    val = strings.TrimSpace(val)
    if len(val) > 140 { return "" }
    return val
}

func claimStrings(ent map[string][]struct {
    Mainsnak struct {
        Datavalue struct { Value json.RawMessage `json:"value"` } `json:"datavalue"`
    } `json:"mainsnak"`
}, prop string) []string {
    var out []string
    for _, claim := range ent[prop] {
        v := claimText(claim.Mainsnak.Datavalue.Value)
        if v != "" { out = append(out, v) }
    }
    return out
}

func isHuman(ent map[string][]struct {
    Mainsnak struct {
        Datavalue struct { Value json.RawMessage `json:"value"` } `json:"datavalue"`
    } `json:"mainsnak"`
}) bool {
    for _, claim := range ent["P31"] {
        var v struct { ID string `json:"id"` }
        if json.Unmarshal(claim.Mainsnak.Datavalue.Value, &v) == nil && v.ID == "Q5" { return true }
    }
    return false
}

func publicPeople(client *http.Client, apiBase, name string) ([]publicPerson, error) {
    name = strings.TrimSpace(name)
    if len(name) < 3 || len(name) > 120 { return nil, errors.New("enter a name (3-120 characters)") }
    p := url.Values{"action":{"wbsearchentities"}, "search":{name},
        "language":{"en"}, "format":{"json"}, "type":{"item"}, "limit":{"5"}}
    var search wikiSearch
    if err := wikiFetch(client, apiBase, p, &search); err != nil { return nil, err }
    var people []publicPerson
    var ids []string
    for _, item := range search.Search {
        if !entityID.MatchString(item.ID) { continue }
        people = append(people, publicPerson{ID:item.ID, Name:item.Label, Description:item.Description})
        ids = append(ids,item.ID)
    }
    if len(people) == 0 { return people, nil }
    // One batch request, not a new HTTP connection per name. Never infer a
    // private identity from a label; only show Wikidata-stated public profiles.
    var entities wikiEntityResponse
    p = url.Values{"action":{"wbgetentities"}, "ids":{strings.Join(ids,"|")},
        "props":{"claims"}, "format":{"json"}}
    if err := wikiFetch(client, apiBase, p, &entities); err != nil {
        // Search hits remain useful even if claims are temporarily unavailable.
        return people, nil
    }
    templates := []struct { property, network, prefix string }{
        {"P2002","X/Twitter","https://x.com/"},
        {"P2003","Instagram","https://www.instagram.com/"},
        {"P2037","GitHub","https://github.com/"},
        {"P2013","Facebook","https://www.facebook.com/"},
        {"P2397","YouTube","https://www.youtube.com/channel/"},
    }
    for i := range people {
        ent, ok := entities.Entities[people[i].ID]
        if !ok || !isHuman(ent.Claims) { continue }
        for _, t := range templates {
            for _, account := range claimStrings(ent.Claims, t.property) {
                // No arbitrary URL in provider data may be opened or emitted.
                if strings.ContainsAny(account,"/\\?#@:") || len(account)>100 { continue }
                people[i].Profiles = append(people[i].Profiles, publicProfile{
                    Network:t.network, URL:t.prefix+url.PathEscape(account),
                })
            }
        }
    }
    return people,nil
}

func runPublicName(name string) {
    head("Public name search")
    info("Source: Wikidata; search results are candidates, not identity proof.")
    persons, err := publicPeople(client, wikidataAPI, name)
    if err != nil {
        warn("Public search unavailable: %v",err)
        info("Requires internet access to www.wikidata.org.")
        return
    }
    if len(persons)==0 { miss("No public Wikidata entries for this spelling."); return }
    for _, p := range persons {
        found("%s (%s)",p.Name,p.ID)
        if p.Description!="" { info("  %s",p.Description) }
        info("  Source: https://www.wikidata.org/wiki/%s",p.ID)
        for _, profile := range p.Profiles {
            emit("~",fmt.Sprintf("  %s: %s [Wikidata claim; verify]",profile.Network,profile.URL))
        }
    }
    info("Names can be shared by different people; verify the correct entry.")
}
