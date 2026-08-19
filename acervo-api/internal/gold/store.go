package gold

import (
	"context"
	"fmt"
	"net/http"
	"sync"
	"time"

	icebergio "github.com/apache/iceberg-go/io"
	"github.com/apache/iceberg-go/table"

	_ "github.com/apache/iceberg-go/io/gocloud" // registra los esquemas s3://
)

// Viaje es una fila del mart: el grano es (mes, zona, hora).
type Viaje struct {
	Mes  string `json:"mes"`
	Zona int32  `json:"zona"`
	Hora int32  `json:"hora"`

	Viajes int64 `json:"viajes"`

	// Cadena y no float64, a proposito. En el lakehouse es `decimal(20,2)`
	// porque sumar millones de double acumula error de coma flotante (Decision
	// 006). Serializarlo como numero JSON lo convierte en un float de 64 bits en
	// cuanto alguien lo parsea, deshaciendo esa decision en el ultimo metro.
	Ingreso string `json:"ingreso"`

	DistanciaTotal   float64 `json:"distancia_total"`
	DuracionMediaSeg float64 `json:"duracion_media_seg"`
}

// Store mantiene el mart en memoria.
//
// Se puede porque gold es chico por construccion: 5,128 filas y 82 KB para un
// mes. Si algun dia no cupiera, la respuesta no es paginar aqui sino revisar el
// grano del mart, que es donde vive esa decision.
//
// El dato solo cambia cuando corre dbt, asi que releer en cada peticion seria
// gastar por nada. Cada `Refresco` se le pregunta a Nessie el snapshot actual
// —una llamada barata que no toca S3— y **solo si cambio** se vuelve a leer.
type Store struct {
	base     string
	ref      string
	tabla    string
	props    map[string]string
	refresco time.Duration
	cliente  *http.Client

	mu         sync.RWMutex
	filas      []Viaje
	snapshotID int64
	revisado   time.Time
}

type Opciones struct {
	NessieURL, NessieRef, Tabla string
	S3Endpoint, S3Region        string
	S3Usuario, S3Secreto        string
	Refresco                    time.Duration
}

func NuevoStore(o Opciones) *Store {
	return &Store{
		base:     o.NessieURL,
		ref:      o.NessieRef,
		tabla:    o.Tabla,
		refresco: o.Refresco,
		cliente:  clienteHTTP(),
		props: map[string]string{
			icebergio.S3EndpointURL:            o.S3Endpoint,
			icebergio.S3AccessKeyID:            o.S3Usuario,
			icebergio.S3SecretAccessKey:        o.S3Secreto,
			icebergio.S3Region:                 o.S3Region,
			icebergio.S3ForceVirtualAddressing: "false", // MinIO va por path
		},
	}
}

// Filas devuelve el mart y el snapshot del que salio, recargando si toca.
func (s *Store) Filas(ctx context.Context) ([]Viaje, int64, error) {
	if err := s.refrescar(ctx, false); err != nil {
		return nil, 0, err
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.filas, s.snapshotID, nil
}

// Refrescar fuerza la comprobacion, ignorando el intervalo. Es lo que usa el
// arranque para fallar temprano si el lakehouse no esta.
func (s *Store) Refrescar(ctx context.Context) error { return s.refrescar(ctx, true) }

func (s *Store) refrescar(ctx context.Context, forzar bool) error {
	s.mu.RLock()
	fresco := !forzar && s.filas != nil && time.Since(s.revisado) < s.refresco
	s.mu.RUnlock()
	if fresco {
		return nil
	}

	puntero, err := ResolverPuntero(ctx, s.cliente, s.base, s.ref, s.tabla)
	if err != nil {
		return err
	}

	s.mu.RLock()
	mismo := s.filas != nil && s.snapshotID == puntero.SnapshotID
	s.mu.RUnlock()
	if mismo {
		// El dato no cambio: se corre el reloj y no se toca MinIO.
		s.mu.Lock()
		s.revisado = time.Now()
		s.mu.Unlock()
		return nil
	}

	filas, err := s.leer(ctx, puntero)
	if err != nil {
		return err
	}

	s.mu.Lock()
	s.filas, s.snapshotID, s.revisado = filas, puntero.SnapshotID, time.Now()
	s.mu.Unlock()
	return nil
}

func (s *Store) leer(ctx context.Context, p Puntero) ([]Viaje, error) {
	fsF := icebergio.LoadFSFunc(s.props, p.MetadataLocation)

	tbl, err := table.NewFromLocation(ctx, []string{s.tabla}, p.MetadataLocation, fsF, nil)
	if err != nil {
		return nil, fmt.Errorf("no se pudo abrir %s en %s: %w", s.tabla, p.MetadataLocation, err)
	}

	at, err := tbl.Scan().ToArrowTable(ctx)
	if err != nil {
		return nil, fmt.Errorf("no se pudo leer %s: %w", s.tabla, err)
	}
	defer at.Release()

	return aViajes(at)
}
