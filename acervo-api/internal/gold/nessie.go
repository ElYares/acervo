// Package gold lee la capa gold del lakehouse.
package gold

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

// Puntero es lo que Nessie sabe de una tabla: donde vive su metadata y en que
// snapshot esta.
type Puntero struct {
	MetadataLocation string
	SnapshotID       int64
}

// ResolverPuntero pregunta a Nessie por su **API nativa**, no por su endpoint
// Iceberg REST.
//
// El REST existe y responde 500 con `Warehouse 'warehouse' is not known`: para
// servirlo habria que configurarle a Nessie el warehouse y darle credenciales
// de S3, que es exactamente lo que el `compose.yaml` evita a proposito. La API
// nativa devuelve la ruta del metadata sin tocar el object store, que es todo
// lo que hace falta: los bytes los lee este proceso con sus propias claves.
func ResolverPuntero(ctx context.Context, cliente *http.Client, base, ref, tabla string) (Puntero, error) {
	destino, err := url.JoinPath(base, "api", "v2", "trees", ref, "contents", tabla)
	if err != nil {
		return Puntero{}, fmt.Errorf("url de nessie invalida: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, destino, nil)
	if err != nil {
		return Puntero{}, err
	}

	res, err := cliente.Do(req)
	if err != nil {
		return Puntero{}, fmt.Errorf("nessie no responde en %s; levanta el stack con `devherd up`: %w", base, err)
	}
	defer res.Body.Close()

	if res.StatusCode == http.StatusNotFound {
		return Puntero{}, fmt.Errorf("la tabla %s no existe en la rama %s; corre `cd transform && uv run dbt run`", tabla, ref)
	}
	if res.StatusCode != http.StatusOK {
		return Puntero{}, fmt.Errorf("nessie devolvio %d para %s", res.StatusCode, tabla)
	}

	var cuerpo struct {
		Content struct {
			Tipo             string `json:"type"`
			MetadataLocation string `json:"metadataLocation"`
			SnapshotID       int64  `json:"snapshotId"`
		} `json:"content"`
	}
	if err := json.NewDecoder(res.Body).Decode(&cuerpo); err != nil {
		return Puntero{}, fmt.Errorf("respuesta de nessie ilegible: %w", err)
	}

	// Nessie versiona mas cosas que tablas Iceberg: una vista o un namespace
	// devuelven 200 con otro `type` y sin `metadataLocation`. Sin este control,
	// el fallo apareceria mucho despues, al abrir un metadata vacio.
	if cuerpo.Content.Tipo != "ICEBERG_TABLE" {
		return Puntero{}, fmt.Errorf("%s no es una tabla Iceberg, es %s", tabla, cuerpo.Content.Tipo)
	}
	if cuerpo.Content.MetadataLocation == "" {
		return Puntero{}, fmt.Errorf("nessie no dio metadataLocation para %s", tabla)
	}

	return Puntero{
		MetadataLocation: cuerpo.Content.MetadataLocation,
		SnapshotID:       cuerpo.Content.SnapshotID,
	}, nil
}

func clienteHTTP() *http.Client {
	return &http.Client{Timeout: 10 * time.Second}
}
