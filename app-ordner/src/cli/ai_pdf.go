package main

// ai_pdf.go: read a small number of public, text-based PDFs returned by a
// search engine. Limit downloads, pages and processing; never crawl networks.
// Image-only PDFs still require OCR, not included in v2.0.

import (
  "bytes"
  "context"
  "errors"
  "fmt"
  "io"
  "net"
  "net/http"
  "net/url"
  "sort"
  "strings"
  "time"

  pdf "rsc.io/pdf"
)

const maxPDFBytes=3*1024*1024

func publicPDFClient() *http.Client {
  transport:=&http.Transport{
    Proxy:nil,
    MaxIdleConns:2,
    IdleConnTimeout:5*time.Second,
    TLSHandshakeTimeout:4*time.Second,
    DialContext:func(ctx context.Context,network,address string)(net.Conn,error){
      host,port,err:=net.SplitHostPort(address)
      if err!=nil{return nil,err}
      ips,err:=net.DefaultResolver.LookupIPAddr(ctx,host)
      if err!=nil{return nil,err}
      for _,ip:=range ips{
        if !isPublicIP(ip.IP){continue}
        conn,err:=(&net.Dialer{Timeout:4*time.Second}).DialContext(ctx,network,net.JoinHostPort(ip.IP.String(),port))
        if err==nil{return conn,nil}
      }
      return nil,errors.New("public PDF destination unavailable")
    },
  }
  return &http.Client{Timeout:9*time.Second,Transport:transport,
    CheckRedirect:func(req *http.Request,via []*http.Request)error {
      if len(via)>1{return http.ErrUseLastResponse}
      if req.URL.Scheme!="https"||req.URL.User!=nil {return http.ErrUseLastResponse}
      return nil
    },
  }
}

func pdfExcerpt(content []byte,phrase string)(excerpt string,page int,err error){
  if len(content)<100||len(content)>maxPDFBytes||!bytes.HasPrefix(content,[]byte("%PDF-")){
    return "",0,errors.New("not a supported text PDF")
  }
  // PDF decoders are complex. Reject panics from malformed public documents
  // rather than losing the whole OSINT program.
  defer func(){
    if recovered:=recover();recovered!=nil{err=errors.New("PDF decoding failed");excerpt="";page=0}
  }()
  r,err:=pdf.NewReader(bytes.NewReader(content),int64(len(content)))
  if err!=nil{return "",0,err}
  pages:=r.NumPage()
  if pages>12{pages=12}
  if pages<1{return "",0,errors.New("PDF without readable pages")}
  needle:=strings.ToLower(strings.Join(strings.Fields(phrase)," "))
  for n:=1;n<=pages;n++{
    tokens:=r.Page(n).Content().Text
    if len(tokens)>30000 {continue}
    sort.SliceStable(tokens,func(i,j int)bool {
      if tokens[i].Y!=tokens[j].Y {return tokens[i].Y>tokens[j].Y}
      return tokens[i].X<tokens[j].X
    })
    var b strings.Builder
    for _,word:=range tokens {
      if b.Len()>200000{break}
      b.WriteString(word.S)
      b.WriteByte(' ')
    }
    text:=strings.Join(strings.Fields(b.String())," ")
    index:=strings.Index(strings.ToLower(text),needle)
    if index<0{continue}
    start:=index-110
    if start<0{start=0}
    end:=index+len(needle)+150
    if end>len(text){end=len(text)}
    return text[start:end],n,nil
  }
  return "",0,errors.New("searched phrase not found in first 12 readable PDF pages")
}

func readPublicPDFExcerpt(rawURL,phrase string)(string,int,error){
  u,err:=url.Parse(publicSourceURL(rawURL))
  if err!=nil || u.Scheme!="https" || u.Host=="" {return "",0,errors.New("invalid source URL")}
  req,err:=http.NewRequest(http.MethodGet,u.String(),nil)
  if err!=nil{return "",0,err}
  req.Header.Set("User-Agent","FlipperOne-OSINT/2.0 (+https://github.com/wasabicover258/FlipperOne-OSINT)")
  req.Header.Set("Accept","application/pdf")
  resp,err:=publicPDFClient().Do(req)
  if err!=nil{return "",0,err}
  defer resp.Body.Close()
  if resp.StatusCode!=200{return "",0,fmt.Errorf("PDF source HTTP %d",resp.StatusCode)}
  if resp.ContentLength>maxPDFBytes{return "",0,errors.New("PDF exceeds size limit")}
  mime:=strings.ToLower(resp.Header.Get("Content-Type"))
  if !strings.Contains(mime,"pdf") &&
    !strings.HasSuffix(strings.ToLower(u.Path),".pdf"){
    return "",0,errors.New("source is not a PDF")
  }
  body,err:=io.ReadAll(io.LimitReader(resp.Body,maxPDFBytes+1))
  if err!=nil{return "",0,err}
  if len(body)>maxPDFBytes{return "",0,errors.New("PDF exceeds 3 MiB limit")}
  return pdfExcerpt(body,phrase)
}
