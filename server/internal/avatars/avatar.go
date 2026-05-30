package avatars

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	DefaultModelType  = "default"
	DefaultModelColor = "Blue"
	MaxHeadPNGB64Len  = 8 * 1024
	MaxHeadPNGBytes   = 8 * 1024
)

var (
	ErrInvalidPayload = errors.New("invalid_avatar_payload")
	pngSignature      = []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}
	colorByLower      = map[string]string{
		"black":  "Black",
		"blue":   "Blue",
		"gray":   "Gray",
		"green":  "Green",
		"purple": "Purple",
		"red":    "Red",
		"white":  "White",
	}
)

type Store struct {
	pool *pgxpool.Pool
}

type Model struct {
	ModelType  string `json:"model_type"`
	ModelColor string `json:"model_color"`
}

type Payload struct {
	Model      Model  `json:"model"`
	HeadPNGB64 string `json:"head_png_b64,omitempty"`
}

type Record struct {
	UserID    string
	Payload   Payload
	UpdatedAt time.Time
}

func NewStore(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

func EnsureSchema(ctx context.Context, pool *pgxpool.Pool) error {
	const q = `
		CREATE TABLE IF NOT EXISTS avatars (
			user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
			model_type text NOT NULL DEFAULT 'default',
			model_color text NOT NULL DEFAULT 'Blue',
			head_png_b64 text NOT NULL DEFAULT '',
			updated_at timestamptz NOT NULL DEFAULT now()
		);

		CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
		BEGIN
			NEW.updated_at = now();
			RETURN NEW;
		END;
		$$ LANGUAGE plpgsql;

		DROP TRIGGER IF EXISTS avatars_touch_updated_at ON avatars;
		CREATE TRIGGER avatars_touch_updated_at
			BEFORE UPDATE ON avatars
			FOR EACH ROW
			EXECUTE FUNCTION touch_updated_at();
	`
	_, err := pool.Exec(ctx, q)
	return err
}

func DefaultPayload() Payload {
	return Payload{
		Model: Model{
			ModelType:  DefaultModelType,
			ModelColor: DefaultModelColor,
		},
	}
}

func NormalizeOrDefault(payload Payload) Payload {
	normalized, err := NormalizePayload(payload)
	if err != nil {
		return DefaultPayload()
	}
	return normalized
}

func NormalizePayload(payload Payload) (Payload, error) {
	modelType := strings.TrimSpace(strings.ToLower(payload.Model.ModelType))
	if modelType == "" {
		modelType = DefaultModelType
	}
	if modelType != DefaultModelType {
		return Payload{}, fmt.Errorf("%w: unknown model_type %q", ErrInvalidPayload, payload.Model.ModelType)
	}

	modelColor := strings.TrimSpace(payload.Model.ModelColor)
	if modelColor == "" {
		modelColor = DefaultModelColor
	}
	normalizedColor, ok := colorByLower[strings.ToLower(modelColor)]
	if !ok {
		return Payload{}, fmt.Errorf("%w: unknown model_color %q", ErrInvalidPayload, payload.Model.ModelColor)
	}

	head := strings.TrimSpace(payload.HeadPNGB64)
	if len(head) > MaxHeadPNGB64Len {
		return Payload{}, fmt.Errorf("%w: head_png_b64 exceeds %d characters", ErrInvalidPayload, MaxHeadPNGB64Len)
	}
	if head != "" {
		raw, err := base64.StdEncoding.DecodeString(head)
		if err != nil {
			return Payload{}, fmt.Errorf("%w: head_png_b64 is not valid base64", ErrInvalidPayload)
		}
		if len(raw) > MaxHeadPNGBytes {
			return Payload{}, fmt.Errorf("%w: decoded head PNG exceeds %d bytes", ErrInvalidPayload, MaxHeadPNGBytes)
		}
		if len(raw) < len(pngSignature) || string(raw[:len(pngSignature)]) != string(pngSignature) {
			return Payload{}, fmt.Errorf("%w: head image must be a PNG", ErrInvalidPayload)
		}
	}

	return Payload{
		Model: Model{
			ModelType:  modelType,
			ModelColor: normalizedColor,
		},
		HeadPNGB64: head,
	}, nil
}

func (s *Store) Get(ctx context.Context, userID string) (Payload, bool, error) {
	const q = `
		SELECT model_type, model_color, head_png_b64
		FROM avatars
		WHERE user_id = $1
	`
	var payload Payload
	err := s.pool.QueryRow(ctx, q, userID).Scan(
		&payload.Model.ModelType,
		&payload.Model.ModelColor,
		&payload.HeadPNGB64,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return DefaultPayload(), false, nil
	}
	if err != nil {
		return Payload{}, false, err
	}
	return NormalizeOrDefault(payload), true, nil
}

func (s *Store) Upsert(ctx context.Context, userID string, payload Payload) (Payload, error) {
	normalized, err := NormalizePayload(payload)
	if err != nil {
		return Payload{}, err
	}
	const q = `
		INSERT INTO avatars (user_id, model_type, model_color, head_png_b64)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (user_id) DO UPDATE
		SET model_type = EXCLUDED.model_type,
		    model_color = EXCLUDED.model_color,
		    head_png_b64 = EXCLUDED.head_png_b64,
		    updated_at = now()
	`
	_, err = s.pool.Exec(ctx, q,
		userID,
		normalized.Model.ModelType,
		normalized.Model.ModelColor,
		normalized.HeadPNGB64,
	)
	if err != nil {
		return Payload{}, err
	}
	return normalized, nil
}
