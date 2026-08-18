// Command acervo-api sirve la capa gold del lakehouse por HTTP.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ElYares/acervo/acervo-api/internal/api"
	"github.com/ElYares/acervo/acervo-api/internal/config"
	"github.com/ElYares/acervo/acervo-api/internal/gold"
)

// Codigos de salida, alineados con `ingest`: 3 es "falta configuracion", que se
// distingue de un fallo de ejecucion porque se arregla en el `.env` y no
// reintentando.
const (
	salidaError  = 1
	salidaConfig = 3
)

func main() {
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))

	cfg, err := config.DesdeEntorno()
	if err != nil {
		log.Error("configuracion invalida", "err", err)
		os.Exit(salidaConfig)
	}

	store := gold.NuevoStore(gold.Opciones{
		NessieURL:  cfg.NessieURL,
		NessieRef:  cfg.NessieRef,
		Tabla:      cfg.Tabla,
		S3Endpoint: cfg.S3Endpoint,
		S3Region:   cfg.S3Region,
		S3Usuario:  cfg.S3Usuario,
		S3Secreto:  cfg.S3Secreto,
		Refresco:   cfg.Refresco,
	})

	// Se lee una vez antes de escuchar. Arrancar y aceptar peticiones para
	// devolverles un 503 a todas seria estar `Up` sin funcionar, que es el modo
	// de fallo que este proyecto ya se comio una vez con Nessie.
	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	err = store.Refrescar(ctx)
	cancelar()
	if err != nil {
		log.Error("no se pudo leer la capa gold al arrancar", "err", err)
		os.Exit(salidaError)
	}

	filas, snapshot, _ := store.Filas(context.Background())
	log.Info("gold cargada", "tabla", cfg.Tabla, "filas", len(filas), "snapshot", snapshot)

	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           api.Nuevo(store, log).Rutas(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	parar := make(chan os.Signal, 1)
	signal.Notify(parar, os.Interrupt, syscall.SIGTERM)

	go func() {
		log.Info("escuchando", "addr", cfg.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("el servidor murio", "err", err)
			os.Exit(salidaError)
		}
	}()

	<-parar
	log.Info("apagando")
	ctx, cancelar = context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelar()
	if err := srv.Shutdown(ctx); err != nil {
		log.Error("apagado sucio", "err", err)
		os.Exit(salidaError)
	}
}
