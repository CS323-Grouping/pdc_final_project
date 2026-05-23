package auth

import "golang.org/x/crypto/bcrypt"

// bcryptCost balances login latency (~200ms on a 1 vCPU box) against attacker
// cost. Bump in lockstep with hardware over time. Existing hashes are NOT
// re-hashed; a future migration could re-hash on next successful login.
const bcryptCost = 12

// dummyPasswordHash is used to burn a bcrypt comparison when a login email
// does not exist. This keeps "unknown email" closer to "bad password" timing.
const dummyPasswordHash = "$2a$12$8oDGSpQQlHCLUcSxlgBjLuWAKEncPaUCRRFpJyHIqwmExLSYO373a"

// HashPassword returns a bcrypt hash suitable for storage in users.password_hash.
func HashPassword(plain string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(plain), bcryptCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

// VerifyPassword constant-time compares the bcrypt hash against the plaintext.
// Returns true on match. Any error (mismatch, malformed hash) → false.
func VerifyPassword(hash, plain string) bool {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(plain)) == nil
}

func BurnPasswordCheck(plain string) {
	_ = VerifyPassword(dummyPasswordHash, plain)
}
