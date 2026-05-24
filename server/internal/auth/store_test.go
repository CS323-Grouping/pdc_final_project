package auth

import (
	"errors"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
)

func TestTranslateUniqueViolation(t *testing.T) {
	tests := []struct {
		name       string
		constraint string
		want       error
	}{
		{name: "email exact", constraint: "users_email_key", want: ErrEmailTaken},
		{name: "email lower", constraint: "users_email_lower_unique_idx", want: ErrEmailTaken},
		{name: "display exact", constraint: "users_display_name_key", want: ErrDisplayNameTaken},
		{name: "display lower", constraint: "users_display_name_lower_unique_idx", want: ErrDisplayNameTaken},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := translateUniqueViolation(&pgconn.PgError{
				Code:           "23505",
				ConstraintName: tt.constraint,
			})
			if !errors.Is(err, tt.want) {
				t.Fatalf("translateUniqueViolation = %v, want %v", err, tt.want)
			}
		})
	}
}

func TestTranslateUniqueViolationLeavesUnknownErrorsAlone(t *testing.T) {
	input := errors.New("boom")
	if got := translateUniqueViolation(input); got != input {
		t.Fatalf("translateUniqueViolation changed non-pg error: %v", got)
	}
}
