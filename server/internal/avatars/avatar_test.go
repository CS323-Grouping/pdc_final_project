package avatars

import (
	"encoding/base64"
	"strings"
	"testing"
)

func TestNormalizePayloadDefaultsModel(t *testing.T) {
	got, err := NormalizePayload(Payload{})
	if err != nil {
		t.Fatalf("NormalizePayload returned err: %v", err)
	}
	if got.Model.ModelType != DefaultModelType {
		t.Fatalf("model_type = %q, want %q", got.Model.ModelType, DefaultModelType)
	}
	if got.Model.ModelColor != DefaultModelColor {
		t.Fatalf("model_color = %q, want %q", got.Model.ModelColor, DefaultModelColor)
	}
}

func TestNormalizePayloadAcceptsSmallPNG(t *testing.T) {
	raw := append([]byte(nil), pngSignature...)
	raw = append(raw, []byte("tiny-test-payload")...)
	payload := Payload{
		Model:      Model{ModelType: "default", ModelColor: "green"},
		HeadPNGB64: base64.StdEncoding.EncodeToString(raw),
	}

	got, err := NormalizePayload(payload)
	if err != nil {
		t.Fatalf("NormalizePayload returned err: %v", err)
	}
	if got.Model.ModelColor != "Green" {
		t.Fatalf("model_color = %q, want Green", got.Model.ModelColor)
	}
	if got.HeadPNGB64 == "" {
		t.Fatalf("head_png_b64 was cleared")
	}
}

func TestNormalizePayloadRejectsOversizedHead(t *testing.T) {
	payload := Payload{
		Model:      Model{ModelType: "default", ModelColor: "Blue"},
		HeadPNGB64: strings.Repeat("A", MaxHeadPNGB64Len+1),
	}

	if _, err := NormalizePayload(payload); err == nil {
		t.Fatalf("NormalizePayload returned nil err, want oversized rejection")
	}
}
