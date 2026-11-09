package main

import (
    "fmt"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"
    "time"
)

func TestPublicPeopleWikidataProfiles(t *testing.T) {
    count := 0
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        count++
        w.Header().Set("Content-Type", "application/json")
        q := r.URL.Query()
        switch q.Get("action") {
        case "wbsearchentities":
            if q.Get("search") != "Donald Trump" {
                t.Errorf("incorrect name: %s", q.Get("search"))
            }
            fmt.Fprint(w, `{"search":[{"id":"Q22686","label":"Donald Trump","description":"American politician"},{"id":"Q66","label":"Donald Trump (band)","description":"band"}]}`)
        case "wbgetentities":
            fmt.Fprint(w, `{"entities":{"Q22686":{"claims":{"P31":[{"mainsnak":{"datavalue":{"value":{"id":"Q5"}}}}],"P2002":[{"mainsnak":{"datavalue":{"value":"realDonaldTrump"}}}],"P2003":[{"mainsnak":{"datavalue":{"value":"realdonaldtrump"}}}]}},"Q66":{"claims":{"P2002":[{"mainsnak":{"datavalue":{"value":"fakeBand"}}}]}}}}`)
        default:
            http.Error(w, "wrong API action", 400)
        }
    }))
    defer server.Close()
    c:=&http.Client{Timeout:2*time.Second}
    entries, err := publicPeople(c, server.URL, " Donald Trump ")
    if err != nil { t.Fatal(err) }
    if count != 2 { t.Fatalf("expected only 2 network requests, got %d",count) }
    if len(entries)!=2 || entries[0].ID!="Q22686" { t.Fatalf("unexpected candidates %#v",entries) }
    if len(entries[0].Profiles)!=2 { t.Fatalf("public profile claims missing: %#v",entries[0]) }
    if entries[0].Profiles[0].URL!="https://x.com/realDonaldTrump" { t.Errorf("wrong X profile %#v",entries[0].Profiles) }
    if len(entries[1].Profiles)!=0 { t.Fatal("non-human entity must not produce personal profiles") }
}

func TestPublicPeopleInputAndError(t *testing.T) {
    if _,err:=publicPeople(http.DefaultClient,"https://wikidata.org/w/api.php","x");err==nil {
        t.Fatal("short names must be rejected")
    }
    s:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
        http.Error(w,"rate limit",429)
    }))
    defer s.Close()
    _,err:=publicPeople(s.Client(),s.URL,"Alice Example")
    if err==nil || !strings.Contains(err.Error(),"429") { t.Fatalf("expected a clear HTTP status: %v",err) }
}
