// Package config lee la configuracion del entorno.
//
// Mismo `.env` unico de la raiz que leen Compose y los servicios de Python. Go
// no trae nada como `python-dotenv`, asi que se busca hacia arriba desde el
// directorio de trabajo: `go run ./cmd/acervo-api` y el binario compilado
// arrancan desde sitios distintos.
//
// **Este servicio si lleva credenciales de MinIO, al reves que `transform`.**
// No es una inconsistencia: `transform` se las pide a Spark porque hay un Spark
// al que pedirselas. Aqui no hay motor delante, el proceso lee los objetos el
// mismo, y no puede delegar en nadie.
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

// ErrFaltaSecreto se devuelve cuando una variable obligatoria no esta puesta.
// La Decision 004 del vault prohibe defaults para secretos: es preferible que
// el proceso muera nombrando la variable a que arranque con una clave inventada
// y falle mucho despues con un 403 que no dice nada.
var ErrFaltaSecreto = errors.New("falta una variable obligatoria")

type Config struct {
	Addr      string
	NessieURL string
	NessieRef string
	Tabla     string

	S3Endpoint string
	S3Region   string
	S3Usuario  string
	S3Secreto  string

	// Cada cuanto se le pregunta a Nessie si hay un snapshot nuevo. No es el
	// tiempo de vida de los datos: si el snapshot no cambio, no se recarga nada.
	Refresco time.Duration
}

func DesdeEntorno() (Config, error) {
	cargarEnv()

	cfg := Config{
		Addr:       opcional("ACERVO_API_ADDR", ":8088"),
		NessieURL:  opcional("ACERVO_NESSIE_URL", "http://localhost:19120"),
		NessieRef:  opcional("ACERVO_NESSIE_REF", "main"),
		Tabla:      opcional("ACERVO_GOLD_TABLA", "gold.viajes_por_zona_hora"),
		S3Endpoint: opcional("ACERVO_S3_ENDPOINT", "http://localhost:9000"),
		S3Region:   opcional("ACERVO_S3_REGION", "us-east-1"),
		S3Usuario:  os.Getenv("MINIO_ROOT_USER"),
		S3Secreto:  os.Getenv("MINIO_ROOT_PASSWORD"),
	}

	for nombre, valor := range map[string]string{
		"MINIO_ROOT_USER":     cfg.S3Usuario,
		"MINIO_ROOT_PASSWORD": cfg.S3Secreto,
	} {
		if valor == "" {
			return Config{}, fmt.Errorf("%w: %s. Corre `cp .env.example .env` en la raiz", ErrFaltaSecreto, nombre)
		}
	}

	segundos, err := strconv.Atoi(opcional("ACERVO_API_REFRESCO_SEG", "30"))
	if err != nil || segundos < 0 {
		return Config{}, fmt.Errorf("ACERVO_API_REFRESCO_SEG debe ser un entero de segundos, no %q", os.Getenv("ACERVO_API_REFRESCO_SEG"))
	}
	cfg.Refresco = time.Duration(segundos) * time.Second

	return cfg, nil
}

// cargarEnv busca el `.env` hacia arriba y lo carga sin pisar lo ya exportado.
// Que no exista no es un error: en un contenedor las variables vienen del
// entorno y no hay archivo. Quien decide si falta algo es la validacion de
// arriba, que nombra la variable concreta.
func cargarEnv() {
	dir, err := os.Getwd()
	if err != nil {
		return
	}
	for {
		ruta := filepath.Join(dir, ".env")
		if _, err := os.Stat(ruta); err == nil {
			_ = godotenv.Load(ruta) // godotenv.Load no pisa lo ya exportado
			return
		}
		padre := filepath.Dir(dir)
		if padre == dir {
			return
		}
		dir = padre
	}
}

func opcional(nombre, porDefecto string) string {
	if v := os.Getenv(nombre); v != "" {
		return v
	}
	return porDefecto
}
