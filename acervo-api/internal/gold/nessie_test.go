package gold

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func servidorFalso(t *testing.T, codigo int, cuerpo string) *httptest.Server {
	t.Helper()
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(codigo)
		_, _ = w.Write([]byte(cuerpo))
	}))
	t.Cleanup(s.Close)
	return s
}

func TestResuelveElPuntero(t *testing.T) {
	s := servidorFalso(t, 200, `{"content":{"type":"ICEBERG_TABLE",
		"metadataLocation":"s3://warehouse/gold/t/metadata/1.json","snapshotId":7}}`)

	p, err := ResolverPuntero(context.Background(), s.Client(), s.URL, "main", "gold.t")
	if err != nil {
		t.Fatal(err)
	}
	if p.SnapshotID != 7 || p.MetadataLocation != "s3://warehouse/gold/t/metadata/1.json" {
		t.Fatalf("puntero = %+v", p)
	}
}

func TestTablaQueNoExiste(t *testing.T) {
	// Nessie da 404 y el mensaje tiene que mandar a correr dbt: sin eso, quien
	// lo lea va a buscar el fallo en el API y no en que gold no se materializo.
	s := servidorFalso(t, 404, `{}`)
	_, err := ResolverPuntero(context.Background(), s.Client(), s.URL, "main", "gold.t")
	if err == nil {
		t.Fatal("quiero error")
	}
	if !strings.Contains(err.Error(), "dbt run") {
		t.Errorf("el error no dice como arreglarlo: %v", err)
	}
}

func TestLoQueNoEsTablaIceberg(t *testing.T) {
	// Nessie versiona mas cosas que tablas. Una vista devuelve 200 y sin este
	// control el fallo saldria mucho despues, al abrir un metadata inexistente.
	s := servidorFalso(t, 200, `{"content":{"type":"ICEBERG_VIEW","snapshotId":1}}`)
	_, err := ResolverPuntero(context.Background(), s.Client(), s.URL, "main", "gold.v")
	if err == nil || !strings.Contains(err.Error(), "ICEBERG_VIEW") {
		t.Fatalf("quiero un error que nombre el tipo, tengo: %v", err)
	}
}

func TestNessieCaido(t *testing.T) {
	_, err := ResolverPuntero(context.Background(), clienteHTTP(), "http://127.0.0.1:1", "main", "gold.t")
	if err == nil || !strings.Contains(err.Error(), "devherd up") {
		t.Fatalf("quiero un error que diga como levantar el stack, tengo: %v", err)
	}
}
