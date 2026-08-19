package gold_test

import (
	"context"
	"os"
	"regexp"
	"testing"
	"time"

	"github.com/ElYares/acervo/acervo-api/internal/config"
	"github.com/ElYares/acervo/acervo-api/internal/gold"
)

// Pruebas contra el stack real: Nessie y MinIO. Requieren `devherd up` y la
// tabla de gold materializada. Sin eso se saltan, igual que las de `transform`.
//
// Se saltan tambien con `go test -short ./...`, que es el equivalente de
// `uv run pytest -m "not integracion"`.

func store(t *testing.T) *gold.Store {
	t.Helper()
	if testing.Short() {
		t.Skip("prueba de integracion; quitar -short para correrla")
	}

	cfg, err := config.DesdeEntorno()
	if err != nil {
		t.Skipf("sin configuracion: %v", err)
	}

	s := gold.NuevoStore(gold.Opciones{
		NessieURL: cfg.NessieURL, NessieRef: cfg.NessieRef, Tabla: cfg.Tabla,
		S3Endpoint: cfg.S3Endpoint, S3Region: cfg.S3Region,
		S3Usuario: cfg.S3Usuario, S3Secreto: cfg.S3Secreto,
		Refresco: cfg.Refresco,
	})

	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelar()
	if err := s.Refrescar(ctx); err != nil {
		t.Skipf("el lakehouse no responde; levanta el stack con `devherd up`: %v", err)
	}
	return s
}

func TestLeeElMartEntero(t *testing.T) {
	filas, snapshot, err := store(t).Filas(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	// El mismo numero que fija CU-003 del lado de dbt. Que las dos capas lo
	// afirmen por separado es lo que detecta que una se movio sin la otra.
	if len(filas) != 5128 {
		t.Errorf("filas = %d, quiero 5128 (yellow 2024-01)", len(filas))
	}
	if snapshot == 0 {
		t.Error("snapshot_id = 0; Nessie no dio snapshot")
	}
}

func TestElIngresoConservaSusDosDecimales(t *testing.T) {
	// Si iceberg-go entregara el decimal como float, esto se veria enseguida:
	// aparecerian valores tipo 652924.7699999999.
	filas, _, err := store(t).Filas(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	dosDecimales := regexp.MustCompile(`^-?\d+\.\d{2}$`)
	for _, v := range filas[:min(200, len(filas))] {
		if !dosDecimales.MatchString(v.Ingreso) {
			t.Fatalf("ingreso = %q, quiero exactamente dos decimales", v.Ingreso)
		}
	}
}

func TestElGranoNoSeDuplica(t *testing.T) {
	filas, _, err := store(t).Filas(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	type clave struct {
		mes        string
		zona, hora int32
	}
	visto := make(map[clave]bool, len(filas))
	for _, v := range filas {
		k := clave{v.Mes, v.Zona, v.Hora}
		if visto[k] {
			t.Fatalf("grano duplicado: %+v", k)
		}
		visto[k] = true
	}
}

func TestNoRelevantePorPeticion(t *testing.T) {
	// El dato solo cambia cuando corre dbt. La segunda lectura tiene que
	// devolver exactamente el mismo respaldo, no una copia nueva: si esto falla,
	// cada peticion HTTP se estaria trayendo el parquet de MinIO otra vez.
	s := store(t)
	ctx := context.Background()

	primera, _, err := s.Filas(ctx)
	if err != nil {
		t.Fatal(err)
	}
	segunda, _, err := s.Filas(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(primera) == 0 || &primera[0] != &segunda[0] {
		t.Error("la segunda lectura reconstruyo el mart; la cache no esta sirviendo")
	}
}

func TestMain(m *testing.M) {
	os.Exit(m.Run())
}
