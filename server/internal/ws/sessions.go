package ws

import "sync"

// SessionRegistry tracks active control WebSocket sessions. Phase 1 keeps this
// in memory because one Go process owns all connections; persistence/reconnect
// semantics land later with room state.
type SessionRegistry struct {
	mu     sync.Mutex
	active map[string]struct{}
}

func NewSessionRegistry() *SessionRegistry {
	return &SessionRegistry{active: make(map[string]struct{})}
}

func (r *SessionRegistry) TryReserve(userID string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.active[userID]; exists {
		return false
	}
	r.active[userID] = struct{}{}
	return true
}

func (r *SessionRegistry) Release(userID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.active, userID)
}
