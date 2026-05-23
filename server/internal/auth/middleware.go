package auth

import (
	"context"
	"net"
	"net/http"
	"strings"
	"sync"

	"golang.org/x/time/rate"
)

type ctxKey string

const userClaimsKey ctxKey = "user_claims"

// BearerMiddleware verifies the `Authorization: Bearer <jwt>` header. On
// success the parsed Claims are stashed in the request context (access via
// ClaimsFrom). On failure writes a 401 JSON error and stops the chain.
type BearerMiddleware struct {
	jwtSecret []byte
}

func NewBearerMiddleware(jwtSecret []byte) *BearerMiddleware {
	return &BearerMiddleware{jwtSecret: jwtSecret}
}

func (m *BearerMiddleware) Wrap(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := r.Header.Get("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			writeError(w, ErrNotAuthenticated)
			return
		}
		tokenStr := strings.TrimPrefix(h, "Bearer ")
		claims, err := VerifyAccessToken(m.jwtSecret, tokenStr)
		if err != nil {
			// ErrTokenExpired surfaces as itself (clients distinguish expired
			// from forged); anything else collapses to not_authenticated.
			if asAuthError(err) != nil {
				writeError(w, err)
			} else {
				writeError(w, ErrNotAuthenticated)
			}
			return
		}
		ctx := context.WithValue(r.Context(), userClaimsKey, claims)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// ClaimsFrom returns the validated Claims previously stashed by
// BearerMiddleware. The bool reports whether the context actually had claims.
func ClaimsFrom(ctx context.Context) (*Claims, bool) {
	c, ok := ctx.Value(userClaimsKey).(*Claims)
	return c, ok
}

// -----------------------------------------------------------------
// Per-IP token bucket rate limiter for sensitive endpoints (login/register).
// -----------------------------------------------------------------

// RateLimiter tracks one token bucket per source IP. Not bounded — for our
// audience size (~50 users) the bucket map stays tiny. Add a TTL eviction
// goroutine if we ever expose this to the public internet at scale.
type RateLimiter struct {
	mu      sync.Mutex
	buckets map[string]*rate.Limiter
	rate    rate.Limit
	burst   int
}

// NewRateLimiter creates a limiter where each IP gets a bucket that allows
// `burst` events instantly, then refills at `r` events per second.
//
// Example: NewRateLimiter(rate.Every(12*time.Second), 5) gives "5 quick
// requests then 1 every 12 seconds" — i.e. up to 5 instant logins + ~5/min
// sustained per source IP.
func NewRateLimiter(r rate.Limit, burst int) *RateLimiter {
	return &RateLimiter{
		buckets: make(map[string]*rate.Limiter),
		rate:    r,
		burst:   burst,
	}
}

func (rl *RateLimiter) Wrap(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := remoteIP(r)
		if !rl.allow(ip) {
			writeError(w, ErrRateLimited)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (rl *RateLimiter) allow(ip string) bool {
	rl.mu.Lock()
	lim, ok := rl.buckets[ip]
	if !ok {
		lim = rate.NewLimiter(rl.rate, rl.burst)
		rl.buckets[ip] = lim
	}
	rl.mu.Unlock()
	return lim.Allow()
}

// remoteIP extracts the client IP. Prefers X-Forwarded-For (set by Caddy in
// prod) and falls back to r.RemoteAddr (direct connect in local dev).
func remoteIP(r *http.Request) string {
	if xf := r.Header.Get("X-Forwarded-For"); xf != "" {
		// First entry is the client; rest are proxies in the chain.
		if idx := strings.IndexByte(xf, ','); idx > 0 {
			return strings.TrimSpace(xf[:idx])
		}
		return strings.TrimSpace(xf)
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
