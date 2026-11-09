package main

import (
 "os"
 "testing"
 "time"
 "net/http"
 "bytes"
 pdf "rsc.io/pdf"
)

// Explicit opt-in, read-only live test; external provider downtime is recorded
// as unavailable rather than fraudulently reported as functional.
func TestLiveAIWebV20(t *testing.T){
 if os.Getenv("OSINT_V20_LIVE")!="1"{t.Skip("external providers are opt-in")}
 c:=&http.Client{Timeout:10*time.Second}
 wiki,err:=wikipediaWebSearch("Ada Lovelace",c)
 if err!=nil{t.Logf("LIVE UNAVAILABLE: Wikipedia: %v",err)}else{
  t.Logf("LIVE OK: Wikipedia results=%d",len(wiki))
  if len(wiki)>0{t.Logf("LIVE WIKI URL: %s",wiki[0].URL)}
 }
 works,err:=openAlexWorksSearch("quantum computing",c)
 if err!=nil{t.Logf("LIVE UNAVAILABLE: OpenAlex: %v",err)}else{
  t.Logf("LIVE OK: OpenAlex works=%d",len(works))
  if len(works)>0{t.Logf("LIVE OPENALEX URL: %s",works[0].URL)}
 }
 // Diagnose how this legacy PDF reader segments glyphs (public W3C sample).
 if resp,raw,e:=get(c,"https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf");e==nil&&resp.StatusCode==200 {
    if reader,e:=pdf.NewReader(bytes.NewReader(raw),int64(len(raw)));e==nil {
        txt:=reader.Page(1).Content().Text
        sample:=""
        for i,v:=range txt {
            if i>=30{break}
            sample+=v.S+" | "
        }
        t.Logf("LIVE PDF GLYPHS: count=%d first=%q",len(txt),sample)
    }
 }
 excerpt,page,err:=readPublicPDFExcerpt(
  "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
  "Dummy PDF file",
 )
 if err!=nil{t.Logf("LIVE UNAVAILABLE OR UNMATCHED: PDF extraction: %v",err)}else{
  t.Logf("LIVE OK: PDF text found page=%d snippet-length=%d",page,len(excerpt))
 }
}
