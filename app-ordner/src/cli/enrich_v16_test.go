package main

import (
 "fmt"
 "net/http"
 "net/http/httptest"
 "strings"
 "testing"
 "time"
)

func TestPOI16OnlyClosestItemsAppear(t *testing.T) {
 // Realistic crowding: a hospital is farther away than 30 cafes.
 // It must NOT jump over closer points simply because it is a hospital.
 var b strings.Builder
 b.WriteString(`{"elements":[`)
 for i:=0;i<40;i++{
  if i>0{b.WriteByte(',')}
  kind:="cafe"
  if i==35{kind="hospital"}
  b.WriteString(fmt.Sprintf(`{"type":"node","id":%d,"lat":%.8f,"lon":11.556722,"tags":{"amenity":"%s","name":"Facility %d"}}`,1000+i,48.086056+float64(i+1)*0.000005,kind,i))
 }
 b.WriteString("]}")
 results,err:=parseNearbyResults([]byte(b.String()),48.086056,11.556722,500)
 if err!=nil{t.Fatal(err)}
 if len(results)!=nearbyResultLimit {t.Fatalf("want nearest %d, got %d",nearbyResultLimit,len(results))}
 prev:=-1
 for i,p:=range results{
  if prev>p.Distance{t.Fatalf("not nearest-first at index %d: %d > %d",i,prev,p.Distance)}
  prev=p.Distance
  if p.ID=="node/1035"{t.Fatal("hospital improperly jumped above closer facilities")}
  if p.ID!=fmt.Sprintf("node/%d",1000+i){t.Fatalf("expected closest ID node/%d, got %s",1000+i,p.ID)}
 }
}
func TestExtraJSONBoundedAndClearFailures(t *testing.T) {
 count:=0
 server:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  count++
  if !strings.Contains(r.Header.Get("User-Agent"),"FlipperOne-OSINT/1.6"){t.Error("missing app UA")}
  if r.URL.Path=="/limit"{http.Error(w,"busy",429);return}
  if r.URL.Path=="/large"{
   _,_ = w.Write([]byte(strings.Repeat(" ",384*1024+10)));return
  }
  w.Header().Set("Content-Type","application/json")
  _,_=w.Write([]byte(`{"ok":true}`))
 }))
 defer server.Close()
 var v struct{OK bool `json:"ok"`}
 c:=&http.Client{Timeout:time.Second}
 if err:=extraJSON(c,server.URL+"/ok",&v);err!=nil || !v.OK{t.Fatalf("good fixture: %v %v",err,v)}
 if err:=extraJSON(c,server.URL+"/limit",&v);err==nil || !strings.Contains(err.Error(),"429"){t.Fatalf("expected 429, got %v",err)}
 if err:=extraJSON(c,server.URL+"/large",&v);err==nil || !strings.Contains(err.Error(),"too large"){t.Fatalf("size limit not enforced: %v",err)}
 if count!=3{t.Fatalf("expected exactly 3 calls got %d",count)}
}
func TestGLEIFOfficialRecordSource(t *testing.T) {
 var r gleifRecord
 r.ID="529900T8BM49AURSDO55"
 r.Attributes.LEI=r.ID
 r.Attributes.Entity.LegalName.Name="Example GmbH"
 r.Attributes.Entity.Status="ACTIVE"
 r.Attributes.Registration.Status="ISSUED"
 r.Attributes.Entity.LegalAddress.City="Berlin"
 r.Attributes.Entity.LegalAddress.Country="DE"
 id,name,status,loc:=normalizeGLEIFRecord(r)
 if id!=r.ID||name!="Example GmbH"||!strings.Contains(status,"ACTIVE")||!strings.Contains(loc,"Berlin"){
  t.Errorf("GLEIF parse mismatch: %s, %s, %s, %s",id,name,status,loc)
 }
 r.Attributes.Entity.LegalName.Name=""
 if id,_,_,_:=normalizeGLEIFRecord(r);id!="" {t.Error("LEI without legal name accepted")}
}
func TestRegionContextNotPersonOwner(t *testing.T){
 if v:=germanDialingArea("+49 89 555123");!strings.Contains(v,"Munich"){
  t.Errorf("wanted historic Munich prefix, got %q",v)
 }
 if v:=germanDialingArea("+49 171 123456");v!="" {t.Errorf("mobile incorrectly mapped: %s",v)}
 if v:=germanPlateContext("B-AB 1234");v!="Berlin" {t.Errorf("plate district: %s",v)}
 if v:=germanPlateContext("ZZ-XY123");v!="" {t.Errorf("unknown district must stay unknown: %s",v)}
}
func TestSafeSourceURL(t *testing.T){
 if trustedSite("file:///etc/passwd")!=""{t.Fatal("unsafe source accepted")}
 if trustedSite("https://example.com/docs")!="https://example.com/docs"{t.Fatal("public HTTPS source rejected")}
}
