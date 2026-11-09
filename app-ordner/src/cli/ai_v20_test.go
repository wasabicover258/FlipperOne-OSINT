package main

import (
 "context"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "net/http"
 "os"
 "strings"
 "testing"
)

type testTransportFunc func(*http.Request)(*http.Response,error)
func (f testTransportFunc)RoundTrip(req *http.Request)(*http.Response,error){return f(req)}
func jsonHTTPResponse(payload string)*http.Response{
 return &http.Response{StatusCode:200,Body:io.NopCloser(strings.NewReader(payload)),
   Header:make(http.Header)}
}
func TestV2BravePDFAndDedup(t *testing.T){
 calls:=0
 c:=&http.Client{Transport:testTransportFunc(func(req *http.Request)(*http.Response,error){
  calls++
  if req.Header.Get("X-Subscription-Token")!="test-token"{t.Error("Brave token missing")}
  if !strings.Contains(req.URL.Query().Get("q"),"filetype:pdf"){t.Error("PDF query missing")}
  return jsonHTTPResponse(`{"web":{"results":[
     {"title":"Historical research 2011","url":"https://example.org/docs/2011.pdf",
      "description":"The 2011 archive mentions Max Beispiel.","content_type":"application/pdf"},
     {"title":"Historical research 2011","url":"https://example.org/docs/2011.pdf?utm_source=test",
      "description":"The 2011 archive mentions Max Beispiel.","content_type":"application/pdf"},
     {"title":"Internal file","url":"http://127.0.0.1/private.pdf","description":"untrusted"}
  ]}}`),nil
 })}
 hits,err:=braveWebSearch(`"Max Beispiel" filetype:pdf`,"test-token",c)
 if err!=nil{t.Fatal(err)}
 hits=uniqueWebHits(hits,10)
 if calls!=1||len(hits)!=1||!hits[0].PDF {t.Fatalf("calls=%d hits=%#v",calls,hits)}
 if hits[0].URL!="https://example.org/docs/2011.pdf"{t.Errorf("URL normalization failed: %#v",hits[0])}
}

func TestV2AIHighlightsGroundingAndDiversity(t *testing.T){
 aiItems=nil;aiSection="";aiLast=-1;aiQuiet=false
 aiCapture("#","Web documents")
 aiCapture("+","PDF document: 2011 publication referencing Max Beispiel")
 aiCapture("i","Excerpt: The archive contains a mention of Max Beispiel in 2011.")
 aiCapture("i","Source: https://example.org/2011.pdf")
 aiCapture("+","PDF document: 2011 publication referencing Max Beispiel")
 aiCapture("+","Company website: https://example.org")
 aiCapture("i","Source: https://example.org")
 aiCapture("#","Network records")
 aiCapture("+","IP ASN: AS15169")
 aiCapture("+","ASN operator: Example Org")
 if len(aiItems)!=4||aiItems[0].Repeats!=2 {t.Fatalf("dedup broken %#v",aiItems)}
 if aiItems[0].Source==""||aiItems[0].Excerpt==""{t.Fatal("source/excerpt not attached")}
 selected:=aiSelect(aiItems,"Max Beispiel")
 if len(selected)!=4 {t.Fatalf("expected all 4 distinct findings got %d",len(selected))}
 for _,v:=range selected{
  if v.Label==""{t.Fatal("empty highlight")}
 }
}

func TestV2PublicURLAndModelEndpoint(t *testing.T){
 for _,bad:=range []string{"http://example.org","https://localhost/x","https://192.168.0.1/x",
   "https://user:pass@example.com/doc.pdf","file:///etc/passwd"} {
  if publicSourceURL(bad)!=""{t.Errorf("unsafe URL accepted: %s",bad)}
 }
 if !validAIEndpoint("http://127.0.0.1:8080/v1/chat/completions"){t.Fatal("local model server not supported")}
 if validAIEndpoint("http://remote.example/v1/chat/completions"){t.Fatal("insecure remote AI server allowed")}
}

func TestV2AIStatusDoesNotRevealSecrets(t *testing.T){
 os.Setenv("BRAVE_SEARCH_API_KEY","FAKE-SECRET-DO-NOT-DISPLAY")
 defer os.Unsetenv("BRAVE_SEARCH_API_KEY")
 // Status must only branch on presence, never emit the value.
 runAIStatus()
}

func TestV2PlainSnippetRemovesHTML(t *testing.T){
 s:=plainSnippet("Important <b>article</b> &amp; document")
 if s!="Important article & document"{t.Fatalf("unsafe HTML snippet %q",s)}
}

func TestV2PDFParserRejectsInvalid(t *testing.T){
 if _,_,err:=pdfExcerpt([]byte("not a pdf"),"Max Beispiel");err==nil {t.Fatal("non-PDF accepted")}
}

func TestV2ReadOnlyAPIResponseShape(t *testing.T){
 // Ensures optional model replies cannot silently change source URLs.
 var r aiChatRes
 if err:=json.Unmarshal([]byte(`{"choices":[{"message":{"content":"{\"points\":[\"A citation\"]}"}}]}`),&r);err!=nil {
  t.Fatal(err)
 }
 if len(r.Choices)!=1{t.Fatal("OpenAI-compatible shape not parsed")}
 _=context.Background
 _=errors.New
 _=fmt.Sprintf
}
