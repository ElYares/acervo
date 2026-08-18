package api

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ElYares/acervo/acervo-api/internal/gold"
)

type fuenteFalsa struct {
	filas []gold.Viaje
	err   error
}

func (f fuenteFalsa) Filas(context.Context) ([]gold.Viaje, int64, error) {
	return f.filas, 42, f.err
}

func mart() []gold.Viaje {
	return []gold.Viaje{
		{Mes: "2024-01", Zona: 132, Hora: 18, Viajes: 7942, Ingreso: "652924.77"},
		{Mes: "2024-01", Zona: 132, Hora: 19, Viajes: 6000, Ingreso: "500000.00"},
		{Mes: "2024-01", Zona: 237, Hora: 18, Viajes: 4000, Ingreso: "80000.00"},
		{Mes: "2024-02", Zona: 132, Hora: 18, Viajes: 100, Ingreso: "9000.00"},
	}
}

func pedir(t *testing.T, fuente Fuente, ruta string) *httptest.ResponseRecorder {
	t.Helper()
	srv := Nuevo(fuente, slog.New(slog.NewTextHandler(io.Discard, nil)))
	w := httptest.NewRecorder()
	srv.Rutas().ServeHTTP(w, httptest.NewRequest(http.MethodGet, ruta, nil))
	return w
}

func TestFiltros(t *testing.T) {
	casos := []struct {
		nombre string
		ruta   string
		quiero int
		total  int
	}{
		{"sin filtro devuelve todo", "/viajes", 4, 4},
		{"por mes", "/viajes?mes=2024-01", 3, 3},
		{"por zona", "/viajes?zona=132", 3, 3},
		{"por hora", "/viajes?hora=18", 3, 3},
		{"combinados", "/viajes?mes=2024-01&zona=132&hora=18", 1, 1},
		{"que no casa nada", "/viajes?zona=999", 0, 0},
		// `total` es lo que casa el filtro y `filas` lo que se devuelve: sin esa
		// distincion, quien pagina no sabe si hay mas.
		{"el limite recorta pero total no miente", "/viajes?limite=2", 2, 4},
		{"limite mayor que el resultado", "/viajes?limite=99", 4, 4},
	}

	for _, c := range casos {
		t.Run(c.nombre, func(t *testing.T) {
			w := pedir(t, fuenteFalsa{filas: mart()}, c.ruta)
			if w.Code != http.StatusOK {
				t.Fatalf("codigo = %d, quiero 200: %s", w.Code, w.Body)
			}
			var r respuestaViajes
			if err := json.Unmarshal(w.Body.Bytes(), &r); err != nil {
				t.Fatal(err)
			}
			if len(r.Viajes) != c.quiero {
				t.Errorf("viajes = %d, quiero %d", len(r.Viajes), c.quiero)
			}
			if r.Filas != c.quiero {
				t.Errorf("filas = %d, quiero %d", r.Filas, c.quiero)
			}
			if r.Total != c.total {
				t.Errorf("total = %d, quiero %d", r.Total, c.total)
			}
			if r.SnapshotID != 42 {
				t.Errorf("snapshot_id = %d, quiero 42", r.SnapshotID)
			}
		})
	}
}

func TestFiltrosInvalidosDan400(t *testing.T) {
	// Un filtro ilegible tiene que ser 400 y no una respuesta vacia con 200:
	// `?hora=25` devolviendo cero filas es indistinguible de "no hubo viajes".
	for _, ruta := range []string{
		"/viajes?hora=25", "/viajes?hora=-1", "/viajes?zona=abc",
		"/viajes?limite=-1", "/viajes?limite=muchos",
	} {
		t.Run(ruta, func(t *testing.T) {
			w := pedir(t, fuenteFalsa{filas: mart()}, ruta)
			if w.Code != http.StatusBadRequest {
				t.Fatalf("codigo = %d, quiero 400", w.Code)
			}
		})
	}
}

func TestSinLakehouseResponde503(t *testing.T) {
	// No 500: el servicio esta bien, lo que no esta es el lakehouse. Un 503 le
	// dice a quien monitorea que reintente en vez de buscar un bug aqui.
	for _, ruta := range []string{"/viajes", "/salud"} {
		w := pedir(t, fuenteFalsa{err: errors.New("nessie no responde")}, ruta)
		if w.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s: codigo = %d, quiero 503", ruta, w.Code)
		}
	}
}

func TestElIngresoViajaComoCadena(t *testing.T) {
	// La Decision 006 puso `decimal` en el lakehouse para no acumular error de
	// coma flotante. Serializarlo como numero JSON lo deshace en la ultima capa:
	// cualquier cliente que lo parsee lo convierte en float64.
	w := pedir(t, fuenteFalsa{filas: mart()}, "/viajes?limite=1")
	var crudo struct {
		Viajes []map[string]json.RawMessage `json:"viajes"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &crudo); err != nil {
		t.Fatal(err)
	}
	if got := string(crudo.Viajes[0]["ingreso"]); got != `"652924.77"` {
		t.Errorf("ingreso = %s, quiero una cadena entrecomillada", got)
	}
}
