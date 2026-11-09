package main

import (
 "net"
 "strings"
 "testing"
)

func TestMultiEntryWebsiteNormalization(t *testing.T) {
 cases:=map[string]string{
  "EXAMPLE.com":"example.com",
  "https://Sub.Example.com/path?q=1":"sub.example.com",
  "http://example.com:8080/x":"example.com",
 }
 for input,want:=range cases{
  got,err:=normalizeWebInput(input)
  if err!=nil||got!=want{t.Fatalf("%q -> %q %v (want %q)",input,got,err,want)}
 }
 for _,bad:=range []string{"file:///etc/passwd","http://localhost/foo","http://127.0.0.1/path",
     "http://example.local","http://evil.com@localhost","abc xyz"} {
   if _,err:=normalizeWebInput(bad);err==nil{t.Errorf("accepted invalid website %q",bad)}
 }
}
func TestGPSParsingAndBounds(t *testing.T) {
 a,b,err:=parseGPS("48.137, 11.575")
 if err!=nil||a!=48.137||b!=11.575{t.Fatalf("wrong GPS parse %v %v %v",a,b,err)}
 for _,bad:=range []string{"91,0","0,-181","Berlin","0,0,0"}{
   if _,_,err:=parseGPS(bad);err==nil{t.Errorf("accepted invalid coordinates %q",bad)}
 }
}
func TestVehicleAndWalletValidation(t *testing.T) {
 if !vinCheckDigit("1HGCM82633A004352") {
  t.Fatal("known test VIN did not pass North American check digit")}
 if vinCheckDigit("1HGCM82633A004353"){t.Fatal("invalid VIN accepted")}
 if !ethRE.MatchString("0x"+strings.Repeat("a",40)){t.Fatal("EVM pattern rejected valid-looking address")}
 if btcRE.MatchString("notawallet"){t.Fatal("invalid wallet accepted")}
}
func TestPublicIPGuard(t *testing.T) {
 for _,s:=range []string{"127.0.0.1","192.168.1.1","::1","fc00::1234","169.254.0.1"}{
  if isPublicIP(net.ParseIP(s)){t.Errorf("local IP %s was treated as public",s)}
 }
 for _,s:=range []string{"8.8.8.8","2606:4700:4700::1111"}{
  if !isPublicIP(net.ParseIP(s)){t.Errorf("public IP %s was rejected",s)}
 }
}
func TestDedupAcrossSourcesAndLinks(t *testing.T) {
 s:=NewStore()
 a:=s.Add(Record{Kind:KindOrg,Value:"Example Org",Evidence:EvUnconfirmed,
  Sources:[]Source{{Module:"wikidata",URL:"https://www.wikidata.org/wiki/Q1"}}})
 b:=s.Add(Record{Kind:KindOrg,Value:"example org",Evidence:EvIndication,
  Sources:[]Source{{Module:"openstreetmap",URL:"https://www.openstreetmap.org/relation/2"}}})
 if a!=b||s.Len()!=1||len(a.Sources)!=2||a.Evidence!=EvIndication {
  t.Fatalf("dedup or source merge broken %#v / %#v",a,b)
 }
 host:="example.com"
 s.Add(Record{Kind:KindHost,Value:host,Evidence:EvIndication})
 s.Link(KindOrg,"Example Org","official website",KindHost,host,EvIndication,"test")
 s.Link(KindOrg,"Example Org","official website",KindHost,host,EvIndication,"test")
 if len(s.edges)!=1 {t.Fatal("duplicate graph edges were not removed")}
}
