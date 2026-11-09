package main

import (
    "encoding/json"
    "fmt"
    "net/http"
    "net/http/httptest"
    "net/url"
    "strings"
    "testing"
    "time"
)

const fixtureNearby = `{
 "elements":[
  {"type":"way","id":101,"center":{"lat":48.08606,"lon":11.55673},
   "tags":{"name":"Beispiel Klinik","healthcare":"clinic","contact:website":"https://klinik.example",
    "contact:phone":"+49 89 123456","contact:email":"info@klinik.example",
    "addr:street":"Beispielstrasse","addr:housenumber":"7","addr:city":"Muenchen"}},
  {"type":"node","id":102,"lat":48.086065,"lon":11.556731,
   "tags":{"name":"Beispiel Klinik","amenity":"clinic"}},
  {"type":"node","id":203,"lat":48.08630,"lon":11.55690,
   "tags":{"name":"Bistro Test","amenity":"restaurant","website":"https://bistro.example",
    "phone":"+49 89 000111"}},
  {"type":"way","id":204,"center":{"lat":48.087,"lon":11.558},
   "tags":{"building":"residential","addr:street":"Private Lane","name":"Private Residence"}}
 ]
}`

func TestPOINearbyParseFacilityNamesContactsAndDedup(t *testing.T) {
    places,err:=parseNearbyResults([]byte(fixtureNearby),48.086056,11.556722,nearbyRadiusMeters)
    if err!=nil {t.Fatal(err)}
    if len(places)!=2 {t.Fatalf("expected clinic and restaurant; got %#v",places)}
    clinic:=places[0]
    if clinic.Name!="Beispiel Klinik" || clinic.Kind!="Clinic" {
        t.Errorf("clinic category/name incorrect: %#v",clinic)
    }
    if clinic.Website!="https://klinik.example"||clinic.Phone!="+49 89 123456"||
       clinic.Email!="info@klinik.example"{
        t.Errorf("clinic public contacts lost: %#v",clinic)
    }
    if clinic.Address!="Beispielstrasse 7, Muenchen"{
        t.Errorf("clinic public address lost: %q",clinic.Address)
    }
    if clinic.SourceURL!="https://www.openstreetmap.org/way/101"{
        t.Errorf("source not authoritative OSM URL: %q",clinic.SourceURL)
    }
    if places[1].Kind!="Restaurant" {t.Errorf("restaurant not recognized: %#v",places[1])}
    if clinic.Distance>15 {t.Errorf("clinic too far away: %dm",clinic.Distance)}
}

func TestOverpassSingleBoundedRequest(t *testing.T) {
    calls:=0
    server:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request) {
        calls++
        if r.Method!="POST" {t.Errorf("expected POST, got %s",r.Method)}
        if !strings.Contains(r.Header.Get("User-Agent"),"FlipperOne-OSINT/1.5"){
            t.Errorf("missing identifiable UA: %q",r.Header.Get("User-Agent"))
        }
        if err:=r.ParseForm();err!=nil {t.Error(err);return}
        q:=r.Form.Get("data")
        for _,want:=range []string{"(around:500,48.086056,11.556722)", "[healthcare]", "[amenity~", "out center 100"}{
            if !strings.Contains(q,want){t.Errorf("missing %q in query %q",want,q)}
        }
        w.Header().Set("Content-Type","application/json")
        _,_ = w.Write([]byte(fixtureNearby))
    }))
    defer server.Close()
    c:=&http.Client{Timeout:2*time.Second}
    places,err:=queryNearbyPlaces(c,server.URL,48.086056,11.556722,500)
    if err!=nil{t.Fatal(err)}
    if calls!=1 || len(places)!=2 {t.Fatalf("calls=%d places=%d",calls,len(places))}
    if _,err:=queryNearbyPlaces(c,server.URL,48,11,1001);err==nil {
        t.Fatal("radius limit not enforced")
    }
    if calls!=1 {t.Fatalf("invalid radius triggered a second API request")}
}

func TestOverpassBusyIsExplained(t *testing.T) {
    srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
        http.Error(w,"rate limit",429)
    }))
    defer srv.Close()
    _,err:=queryNearbyPlaces(srv.Client(),srv.URL,48.086056,11.556722,500)
    if err==nil || !strings.Contains(err.Error(),"429") {t.Fatalf("expected 429 status, got %v",err)}
}

func TestPOIGraphKeepsPlaceAndBusinessContactsSeparate(t *testing.T) {
    places,err:=parseNearbyResults([]byte(fixtureNearby),48.086056,11.556722,500)
    if err!=nil {t.Fatal(err)}
    saved:=store
    store=NewStore()
    defer func(){store=saved}()
    reportNearbyPlace(places[0],false,map[string]bool{})
    p:=store.byKey[normKey(KindPlace,"way/101")]
    if p==nil || p.Title!="Beispiel Klinik" {t.Errorf("place not identified by stable ID")}
    if store.byKey[normKey(KindPhone,"+49 89 123456")]==nil {t.Error("public clinic phone missing")}
    if store.byKey[normKey(KindEmail,"info@klinik.example")]==nil {t.Error("public clinic email missing")}
    if store.byKey[normKey(KindHost,"klinik.example")]==nil {t.Error("website host missing")}
    if len(store.edges)!=3 {t.Errorf("expected 3 sourced relationships (phone/email/site), got %d",len(store.edges))}
    // Repeating a provider response must not duplicate graph nodes/edges.
    reportNearbyPlace(places[0],false,map[string]bool{})
    if len(store.edges)!=3 {t.Error("repeated source duplicated relations")}
}

func TestPOIRejectsNonFacilitiesAndPrivateListing(t *testing.T) {
    raw:=[]byte(`{"elements":[
      {"type":"node","id":1,"lat":48.086,"lon":11.557,"tags":{"building":"house","name":"Home"}},
      {"type":"node","id":2,"lat":48.086,"lon":11.557,"tags":{"amenity":"hospital","name":"Community Clinic"}}
    ]}`)
    out,err:=parseNearbyResults(raw,48.086056,11.556722,500)
    if err!=nil || len(out)!=1 || out[0].Name!="Community Clinic"{
        t.Errorf("nonpublic feature was not filtered: %#v, %v",out,err)
    }
}

func TestValidPublicBusinessInputFields(t *testing.T) {
    for _,tc:=range []struct{v string; want bool}{
        {"kontakt@klinikum.example",true},
        {"someone@example.com\nInjected",false},
        {"invalid-email",false},
        {"",false},
    }{
        if got:=likelyPublicBusinessEmail(tc.v);got!=tc.want{t.Errorf("%q -> %t, expected %t",tc.v,got,tc.want)}
    }
    q:=buildNearbyQuery(48.086056,11.556722,9999)
    if !strings.Contains(q,"around:1000,"){t.Errorf("radius wasn't capped: %s",q)}
    if len(q)>2000{t.Errorf("overpass query grew unexpectedly: %d",len(q))}
    u:=url.Values{"data":{q}}
    if values,err:=url.ParseQuery(u.Encode());err!=nil || values.Get("data")!=q {
        t.Errorf("overpass query doesn't URL-encode correctly")
    }
    var result nearbyResponse
    if err:=json.Unmarshal([]byte(fixtureNearby),&result);err!=nil || len(result.Elements)!=4 {
        t.Fatalf("fixture format incompatible: %v",err)
    }
    _=fmt.Sprintf("%d",len(result.Elements))
}
