// Package api expone la capa gold por HTTP. Solo lectura: nada aqui escribe al
// lakehouse, porque mezclar las dos cosas convierte el API en un segundo camino
// de escritura sin linaje.
package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/ElYares/acervo/acervo-api/internal/gold"
)

// Fuente es de donde salen las filas. Es una interfaz y no el *gold.Store
// concreto para que las pruebas del transporte HTTP —filtros, codigos, forma del
// JSON— no necesiten un lakehouse levantado. Lo que si lo necesita es la prueba
// del propio Store, que esta en su paquete.
type Fuente interface {
	Filas(ctx context.Context) ([]gold.Viaje, int64, error)
}

type Servidor struct {
	store Fuente
	log   *slog.Logger
}

func Nuevo(store Fuente, log *slog.Logger) *Servidor {
	return &Servidor{store: store, log: log}
}

func (s *Servidor) Rutas() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /salud", s.salud)
	mux.HandleFunc("GET /viajes", s.viajes)
	return mux
}

type respuestaViajes struct {
	// De que snapshot de Iceberg salio esto. Sin el, dos respuestas distintas
	// serian indistinguibles de un error, y con el se puede decir "esto es de
	// antes del ultimo dbt run".
	SnapshotID int64        `json:"snapshot_id"`
	Filas      int          `json:"filas"`
	Total      int          `json:"total"`
	Viajes     []gold.Viaje `json:"viajes"`
}

func (s *Servidor) viajes(w http.ResponseWriter, r *http.Request) {
	filas, snapshot, err := s.store.Filas(r.Context())
	if err != nil {
		s.error(w, http.StatusServiceUnavailable, err)
		return
	}

	filtro, err := leerFiltro(r)
	if err != nil {
		s.error(w, http.StatusBadRequest, err)
		return
	}

	elegidas := make([]gold.Viaje, 0, len(filas))
	for _, v := range filas {
		if filtro.acepta(v) {
			elegidas = append(elegidas, v)
		}
	}

	total := len(elegidas)
	if filtro.limite > 0 && len(elegidas) > filtro.limite {
		elegidas = elegidas[:filtro.limite]
	}

	s.json(w, http.StatusOK, respuestaViajes{
		SnapshotID: snapshot,
		Filas:      len(elegidas),
		Total:      total,
		Viajes:     elegidas,
	})
}

// salud comprueba el camino entero —Nessie y MinIO— y no solo que el proceso
// este vivo. Un `/salud` que siempre devuelve 200 es exactamente el problema que
// este repo ya tuvo con Nessie: `Up` no significa que funcione.
func (s *Servidor) salud(w http.ResponseWriter, r *http.Request) {
	filas, snapshot, err := s.store.Filas(r.Context())
	if err != nil {
		s.error(w, http.StatusServiceUnavailable, err)
		return
	}
	s.json(w, http.StatusOK, map[string]any{
		"estado":      "ok",
		"snapshot_id": snapshot,
		"filas":       len(filas),
	})
}

func (s *Servidor) json(w http.ResponseWriter, codigo int, cuerpo any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(codigo)
	if err := json.NewEncoder(w).Encode(cuerpo); err != nil {
		s.log.Error("no se pudo escribir la respuesta", "err", err)
	}
}

func (s *Servidor) error(w http.ResponseWriter, codigo int, err error) {
	if codigo >= 500 {
		s.log.Error("fallo sirviendo", "codigo", codigo, "err", err)
	}
	s.json(w, codigo, map[string]string{"error": err.Error()})
}

type filtro struct {
	mes        string
	zona, hora *int32
	limite     int
}

func leerFiltro(r *http.Request) (filtro, error) {
	q := r.URL.Query()
	f := filtro{mes: q.Get("mes")}

	var err error
	if f.zona, err = entero32(q.Get("zona"), "zona"); err != nil {
		return filtro{}, err
	}
	if f.hora, err = entero32(q.Get("hora"), "hora"); err != nil {
		return filtro{}, err
	}
	if f.hora != nil && (*f.hora < 0 || *f.hora > 23) {
		return filtro{}, errFiltro("hora tiene que estar entre 0 y 23")
	}

	if v := q.Get("limite"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			return filtro{}, errFiltro("limite tiene que ser un entero no negativo")
		}
		f.limite = n
	}
	return f, nil
}

func (f filtro) acepta(v gold.Viaje) bool {
	switch {
	case f.mes != "" && v.Mes != f.mes:
		return false
	case f.zona != nil && v.Zona != *f.zona:
		return false
	case f.hora != nil && v.Hora != *f.hora:
		return false
	}
	return true
}

func entero32(valor, nombre string) (*int32, error) {
	if valor == "" {
		return nil, nil
	}
	n, err := strconv.ParseInt(valor, 10, 32)
	if err != nil {
		return nil, errFiltro(nombre + " tiene que ser un entero")
	}
	v := int32(n)
	return &v, nil
}

type errFiltro string

func (e errFiltro) Error() string { return string(e) }
