package auth

import (
	"net/http"
	"net/netip"
	"testing"
)

func TestRemoteIPIgnoresForwardedForFromUntrustedPeer(t *testing.T) {
	r := &http.Request{
		RemoteAddr: "203.0.113.10:12345",
		Header: http.Header{
			"X-Forwarded-For": []string{"198.51.100.9"},
		},
	}

	got := remoteIP(r, nil)
	if got != "203.0.113.10" {
		t.Fatalf("remoteIP = %q, want direct peer", got)
	}
}

func TestRemoteIPTrustsForwardedForFromConfiguredProxy(t *testing.T) {
	proxyCIDR := netip.MustParsePrefix("127.0.0.1/32")
	r := &http.Request{
		RemoteAddr: "127.0.0.1:54321",
		Header: http.Header{
			"X-Forwarded-For": []string{"198.51.100.9, 127.0.0.1"},
		},
	}

	got := remoteIP(r, []netip.Prefix{proxyCIDR})
	if got != "198.51.100.9" {
		t.Fatalf("remoteIP = %q, want forwarded client", got)
	}
}
