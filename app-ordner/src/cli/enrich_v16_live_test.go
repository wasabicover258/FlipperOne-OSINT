package main

// A separately triggered, read-only smoke test. It is NOT part of regular
// unit testing or the AppImage packaging CI because public APIs may be busy.
// Invoke with OSINT_V16_LIVE=1. Uses only public example entities.
import (
 "net/http"
 "os"
 "testing"
 "time"
)

func TestLiveV16Sources(t *testing.T) {
 if os.Getenv("OSINT_V16_LIVE")!="1" {t.Skip("external API checks are opt-in")}
 c:=&http.Client{Timeout:4500*time.Millisecond}
 test:=func(label,url string,ok func()bool,body any) {
  t.Run(label,func(t *testing.T){
   err:=extraJSON(c,url,body)
   if err!=nil{t.Logf("LIVE UNAVAILABLE: %s: %v",label,err);return}
   if !ok(){t.Logf("LIVE RESPONDED BUT NO MATCHING RESULTS: %s",label);return}
   t.Logf("LIVE OK: %s; endpoint returned usable JSON",label)
  })
 }
 var authors openAlexAuthors
 test("OpenAlex","https://api.openalex.org/authors?search=Albert%20Einstein&per-page=1",
   func()bool{return len(authors.Results)>0},&authors)
 var gh githubUserProfile
 test("GitHubREST","https://api.github.com/users/octocat",
   func()bool{return gh.Login=="octocat"},&gh)
 var geo extraIPWho
 test("IPWhois","https://ipwho.is/8.8.8.8",
   func()bool{return geo.Success && geo.IP=="8.8.8.8"},&geo)
 var lei gleifRecords
 test("GLEIF","https://api.gleif.org/api/v1/lei-records?filter%5Bentity.legalName%5D=Apple&page%5Bsize%5D=2",
   func()bool{return len(lei.Data)>0},&lei)
 var bgp bgpStatus
 test("RIPEstat","https://stat.ripe.net/data/routing-status/data.json?resource=AS15169",
   func()bool{return bgp.Data.Resource!=""},&bgp)
 var archive archiveAvailability
 test("Wayback","https://archive.org/wayback/available?url=example.com",
   func()bool{return archive.ArchivedSnapshots.Closest.URL!=""},&archive)
 var wmi wmiResponse
 test("NHTSAWMI","https://vpic.nhtsa.dot.gov/api/vehicles/DecodeWMI/1HG?format=json",
   func()bool{return len(wmi.Results)>0},&wmi)
 var btc bitcoinAddressStats
 const genesis="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
 test("BlockstreamBTC","https://blockstream.info/api/address/"+genesis,
   func()bool{return btc.Address==genesis},&btc)
 t.Run("WikipediaGeoSearch",func(t *testing.T){
  var g geoWikiResult
  endpoint:="https://en.wikipedia.org/w/api.php?action=query&list=geosearch&gscoord=48.137%7C11.575&gsradius=1000&gslimit=5&format=json"
  err:=extraJSON(c,endpoint,&g)
  if err!=nil{t.Logf("LIVE UNAVAILABLE: Wikipedia: %v",err);return}
  t.Logf("LIVE OK: Wikipedia GeoSearch returned %d public articles",len(g.Query.GeoSearch))
 })
 t.Run("OverpassNearby",func(t *testing.T){
  places,err:=queryNearbyPlaces(&http.Client{Timeout:18*time.Second},
    overpassEndpoint,48.086056,11.556722,500)
  if err!=nil{t.Logf("LIVE UNAVAILABLE: Overpass: %v",err);return}
  t.Logf("LIVE OK: Overpass parsed %d nearby public POIs",len(places))
  for i,p:=range places {
   if i>=3{break}
   t.Logf("  public POI #%d: type=%s distance=%dm source=%s",i+1,p.Kind,p.Distance,p.SourceURL)
  }
 })
 // Verify response parsing without collecting private identities or probing
 // unrelated networks. The test never attempts email or phone lookups.
}
