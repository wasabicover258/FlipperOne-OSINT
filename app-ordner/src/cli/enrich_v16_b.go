package main

import (
 "fmt"
 "net/url"
 "regexp"
 "strconv"
 "strings"
)

var leiPattern=regexp.MustCompile(`^[A-Z0-9]{20}$`)

type gleifRecords struct{
 Data []gleifRecord `json:"data"`
}
type gleifRecord struct{
 ID string `json:"id"`
 Attributes struct {
  LEI string `json:"lei"`
  Entity struct {
   LegalName struct{Name string `json:"name"`} `json:"legalName"`
   Status string `json:"status"`
   LegalJurisdiction string `json:"legalJurisdiction"`
   LegalAddress struct {
    City string `json:"city"`
    Country string `json:"country"`
    AddressLines []string `json:"addressLines"`
   } `json:"legalAddress"`
  } `json:"entity"`
  Registration struct {
   Status string `json:"status"`
  } `json:"registration"`
 } `json:"attributes"`
}
type gleifSingle struct{
 Data gleifRecord `json:"data"`
}
func normalizeGLEIFRecord(r gleifRecord) (id,name,status,loc string) {
 id=strings.ToUpper(strings.TrimSpace(r.Attributes.LEI))
 if id==""{id=strings.ToUpper(strings.TrimSpace(r.ID))}
 if !leiPattern.MatchString(id){return "","","",""}
 name=strings.TrimSpace(r.Attributes.Entity.LegalName.Name)
 if name==""{return "","","",""}
 status=strings.TrimSpace(r.Attributes.Entity.Status)
 if r.Attributes.Registration.Status!=""{
    status+=" / LEI "+r.Attributes.Registration.Status
 }
 a:=r.Attributes.Entity.LegalAddress
 loc=strings.Join(filterEmpty(strings.Join(a.AddressLines," "),a.City,a.Country),", ")
 return id,name,status,loc
}
func showGLEIFEntity(r gleifRecord,query string){
 lei,name,status,place:=normalizeGLEIFRecord(r)
 if lei==""{return}
 link:="https://search.gleif.org/#/record/"+lei
 found("GLEIF legal entity: %s",shorten(name,100))
 found("Legal Entity Identifier: %s",lei)
 if status!="" {info("Recorded status: %s",shorten(status,70))}
 if place!="" {info("Legal address: %s",shorten(place,95))}
 info("Official registry source: %s",link)
 store.Add(Record{Kind:KindOrg,Value:name,Title:"GLEIF legal entity",Evidence:EvIndication,
  Sources:sourced("gleif","Global Legal Entity Identifier record",link),URL:link})
 store.Add(Record{Kind:KindMeta,Value:lei,Title:"Legal Entity Identifier",
  Evidence:EvIndication,Sources:sourced("gleif","Official corporate identifier",link)})
 store.Link(KindOrg,name,"identified by LEI",KindMeta,lei,EvIndication,link)
 // Multiple similar company names remain independent candidates.
 if !strings.EqualFold(strings.TrimSpace(name),strings.TrimSpace(query)) {
  info("Candidate only: legal name differs from search text.")
 }
}
// 10+11/16: GLEIF legal-entity search independent of Wikidata and OSM.
func extraGLEIFCompany(query string) {
 query=strings.TrimSpace(query)
 if len(query)<3 || len(query)>100 {return}
 head("Official legal entity candidates (GLEIF)")
 q:=url.Values{"filter[entity.legalName]":{query},"page[size]":{"3"}}
 endpoint:="https://api.gleif.org/api/v1/lei-records?"+q.Encode()
 var out gleifRecords
 if err:=extraJSON(extraClient,endpoint,&out);err!=nil{extraMsg("GLEIF legal entity index",err);return}
 if len(out.Data)==0 {info("No matching public LEI entry; many organizations have no LEI.");return}
 for _,r:=range out.Data{showGLEIFEntity(r,query)}
}
// 12/16: actual LEI-registry lookup by an *exact* full-length identifier.
func extraGLEIFRegistry(reg string) bool {
 id:=strings.ToUpper(strings.ReplaceAll(strings.TrimSpace(reg)," ",""))
 if !leiPattern.MatchString(id){return false}
 head("Direct GLEIF registry lookup")
 var out gleifSingle
 endpoint:="https://api.gleif.org/api/v1/lei-records/"+id
 if err:=extraJSON(extraClient,endpoint,&out);err!=nil {
  extraMsg("GLEIF direct LEI",err);return true
 }
 normalized,_,_,_:=normalizeGLEIFRecord(out.Data)
 if normalized!=id {info("Provider returned a different ID; no match accepted.");return true}
 showGLEIFEntity(out.Data,"")
 return true
}

// 13/16: non-sensitive, offline context for a small curated set of
// *German registration district prefixes*. Not a vehicle/owner lookup.
var germanPlateDistricts=map[string]string{
 "B":"Berlin","M":"Munich","HH":"Hamburg","F":"Frankfurt am Main",
 "K":"Cologne","S":"Stuttgart","D":"Duesseldorf","L":"Leipzig",
 "DD":"Dresden","N":"Nuremberg","HB":"Bremen","H":"Hanover",
 "DO":"Dortmund","E":"Essen","A":"Augsburg","AC":"Aachen",
 "DA":"Darmstadt","SB":"Saarbruecken","KL":"Kaiserslautern",
 "RO":"Rosenheim","MUC":"Munich (custom plate, verify district)",
}
func germanPlateContext(input string) string {
 v:=strings.ToUpper(strings.TrimSpace(input))
 // Prefix can have 1-3 letters. Do not guess any resident or vehicle data.
 k:=""
 for _,r:=range v{
  if r>='A' && r<='Z' && len(k)<3 {k+=string(r)} else {break}
 }
 if city,ok:=germanPlateDistricts[k];ok{return city}
 return ""
}
func extraPlateRegion(raw string){
 district:=germanPlateContext(raw)
 if district=="" {return}
 head("Registration district context (Germany)")
 found("Prefix may correspond to: %s",district)
 info("A plate prefix does not establish a vehicle's current location or owner.")
}

// 14/16: second official NHTSA route: decode the VIN's World Manufacturer
// Identifier (positions 1..3). Independent of the existing DecodeVinValues.
type wmiResponse struct {
 Results []struct {
  Name string `json:"Name"`
  ManufacturerId int `json:"ManufacturerId"`
  VehicleType string `json:"VehicleType"`
  Country string `json:"Country"`
 } `json:"Results"`
}
func extraVINWMI(vin string){
 vin=strings.ToUpper(strings.TrimSpace(vin))
 if !vinRE.MatchString(vin){return}
 head("Manufacturer registry (NHTSA WMI)")
 wmi:=vin[:3]
 var result wmiResponse
 api:="https://vpic.nhtsa.dot.gov/api/vehicles/DecodeWMI/"+url.PathEscape(wmi)+"?format=json"
 if err:=extraJSON(extraClient,api,&result);err!=nil{extraMsg("NHTSA WMI",err);return}
 if len(result.Results)==0 {info("WMI not found in public NHTSA manufacturer data");return}
 seen:=map[string]bool{}
 for _,p:=range result.Results {
  name:=strings.TrimSpace(p.Name)
  if name=="" || seen[name] {continue}
  seen[name]=true
  found("WMI manufacturer candidate: %s",shorten(name,100))
  if p.VehicleType!="" {info("Manufacturer vehicle type: %s",p.VehicleType)}
  if p.Country!="" {info("Registered manufacturer country: %s",p.Country)}
  if len(seen)>=3{break}
 }
 info("NHTSA WMI identifies a manufacturer code, not any vehicle owner.")
}

// 15/16: public BTC blockchain statistics. Do not infer identities from
// wallets or perform address clustering. EVM addresses have chain ambiguity.
type bitcoinAddressStats struct {
 Address string `json:"address"`
 ChainStats struct {
  TxCount int64 `json:"tx_count"`
  Funded int64 `json:"funded_txo_sum"`
  Spent int64 `json:"spent_txo_sum"`
 } `json:"chain_stats"`
 MempoolStats struct{
  TxCount int64 `json:"tx_count"`
 } `json:"mempool_stats"`
}
func extraBitcoinBalance(addr string){
 if !btcRE.MatchString(addr){return}
 head("Public BTC chain activity (Blockstream)")
 endpoint:="https://blockstream.info/api/address/"+url.PathEscape(addr)
 var out bitcoinAddressStats
 if err:=extraJSON(extraClient,endpoint,&out);err!=nil {extraMsg("Blockstream Esplora",err);return}
 if out.Address!=addr {info("Blockchain address did not match provider response");return}
 balance:=out.ChainStats.Funded-out.ChainStats.Spent
 if balance<0{warn("Inconsistent blockchain stats from provider");return}
 found("Bitcoin confirmed transactions: %d",out.ChainStats.TxCount)
 found("Bitcoin confirmed balance: %.8f BTC",float64(balance)/1e8)
 info("Mempool transactions: %d",out.MempoolStats.TxCount)
 info("Source: %s",endpoint)
 info("Transactions cannot establish the human owner of this address.")
}

// 16/16: independently observed BGP routing status from RIPE RIS.
type bgpStatus struct{
 Data struct{
  Resource string `json:"resource"`
  V4 struct{Prefixes int `json:"prefixes"`} `json:"v4"`
  V6 struct{Prefixes int `json:"prefixes"`} `json:"v6"`
  ObservedNeighbours int `json:"observed_neighbours"`
  QueryTime string `json:"query_time"`
 } `json:"data"`
}
func extraASNRouting(value string){
 a:=strings.ToUpper(strings.TrimSpace(value))
 m:=asnRE.FindStringSubmatch(a)
 if m==nil{return}
 n,err:=strconv.ParseUint(m[1],10,32)
 if err!=nil||n==0{return}
 id:=fmt.Sprintf("AS%d",n)
 endpoint:="https://stat.ripe.net/data/routing-status/data.json?resource="+id
 head("Independent BGP routing evidence (RIPE RIS)")
 var out bgpStatus
 if err:=extraJSON(extraClient,endpoint,&out);err!=nil {extraMsg("RIPE routing status",err);return}
 if out.Data.Resource!="" && out.Data.Resource!=id {
  info("RIPE returned mismatched resource: ignored");return
 }
 found("Observed IPv4 routing prefixes: %d",out.Data.V4.Prefixes)
 found("Observed IPv6 routing prefixes: %d",out.Data.V6.Prefixes)
 info("BGP neighbours observed: %d",out.Data.ObservedNeighbours)
 if out.Data.QueryTime!=""{info("Routing snapshot: %s",out.Data.QueryTime)}
 info("Source: %s",endpoint)
}
