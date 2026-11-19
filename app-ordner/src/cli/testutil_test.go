package main

import (
	"crypto/x509"
	"sync"
	"time"
)

func syncOnceReset() sync.Once { return sync.Once{} }

func fakeCert(notAfter time.Time) *x509.Certificate { return &x509.Certificate{NotAfter: notAfter} }
