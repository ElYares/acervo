package gold

import (
	"fmt"

	"github.com/apache/arrow-go/v18/arrow"
	"github.com/apache/arrow-go/v18/arrow/array"
)

// aViajes convierte la tabla Arrow que devuelve iceberg-go en filas del dominio.
//
// Se hace por nombre de columna y no por posicion: el orden de las columnas de
// un modelo dbt no es un contrato, y leer por indice convertiria un `select`
// reordenado en datos cruzados sin ningun error.
func aViajes(at arrow.Table) ([]Viaje, error) {
	col := func(nombre string) (*arrow.Column, error) {
		for i := 0; i < int(at.NumCols()); i++ {
			if c := at.Column(i); c.Name() == nombre {
				return c, nil
			}
		}
		return nil, fmt.Errorf("el mart no tiene la columna %q; corre `cd transform && uv run dbt run`", nombre)
	}

	nombres := []string{"mes", "pu_location_id", "hora", "viajes", "ingreso", "distancia_total", "duracion_media_seg"}
	cols := make(map[string]*arrow.Column, len(nombres))
	for _, n := range nombres {
		c, err := col(n)
		if err != nil {
			return nil, err
		}
		cols[n] = c
	}

	filas := make([]Viaje, 0, at.NumRows())

	// Arrow entrega las columnas en trozos, y no tienen por que estar cortados
	// igual. Recorrer por trozo de cada columna a la vez solo es correcto si los
	// cortes coinciden, asi que se aplanan primero.
	mes, err := textos(cols["mes"])
	if err != nil {
		return nil, err
	}
	zona, err := enteros32(cols["pu_location_id"])
	if err != nil {
		return nil, err
	}
	hora, err := enteros32(cols["hora"])
	if err != nil {
		return nil, err
	}
	viajes, err := enteros64(cols["viajes"])
	if err != nil {
		return nil, err
	}
	ingreso, err := decimales(cols["ingreso"])
	if err != nil {
		return nil, err
	}
	distancia, err := reales(cols["distancia_total"])
	if err != nil {
		return nil, err
	}
	duracion, err := reales(cols["duracion_media_seg"])
	if err != nil {
		return nil, err
	}

	for i := range mes {
		filas = append(filas, Viaje{
			Mes:              mes[i],
			Zona:             zona[i],
			Hora:             hora[i],
			Viajes:           viajes[i],
			Ingreso:          ingreso[i],
			DistanciaTotal:   distancia[i],
			DuracionMediaSeg: duracion[i],
		})
	}
	return filas, nil
}

func textos(c *arrow.Column) ([]string, error) {
	out := make([]string, 0, c.Len())
	for _, trozo := range c.Data().Chunks() {
		a, ok := trozo.(*array.String)
		if !ok {
			return nil, fmt.Errorf("%s no es texto sino %s", c.Name(), c.DataType())
		}
		for i := 0; i < a.Len(); i++ {
			out = append(out, a.Value(i))
		}
	}
	return out, nil
}

func enteros32(c *arrow.Column) ([]int32, error) {
	out := make([]int32, 0, c.Len())
	for _, trozo := range c.Data().Chunks() {
		a, ok := trozo.(*array.Int32)
		if !ok {
			return nil, fmt.Errorf("%s no es int32 sino %s", c.Name(), c.DataType())
		}
		out = append(out, a.Int32Values()...)
	}
	return out, nil
}

func enteros64(c *arrow.Column) ([]int64, error) {
	out := make([]int64, 0, c.Len())
	for _, trozo := range c.Data().Chunks() {
		a, ok := trozo.(*array.Int64)
		if !ok {
			return nil, fmt.Errorf("%s no es int64 sino %s", c.Name(), c.DataType())
		}
		out = append(out, a.Int64Values()...)
	}
	return out, nil
}

func reales(c *arrow.Column) ([]float64, error) {
	out := make([]float64, 0, c.Len())
	for _, trozo := range c.Data().Chunks() {
		a, ok := trozo.(*array.Float64)
		if !ok {
			return nil, fmt.Errorf("%s no es float64 sino %s", c.Name(), c.DataType())
		}
		out = append(out, a.Float64Values()...)
	}
	return out, nil
}

// decimales devuelve el importe como cadena con su escala exacta. Convertirlo a
// float64 aqui desharia la Decision 006 en la ultima capa del sistema.
func decimales(c *arrow.Column) ([]string, error) {
	tipo, ok := c.DataType().(*arrow.Decimal128Type)
	if !ok {
		return nil, fmt.Errorf("%s no es decimal128 sino %s", c.Name(), c.DataType())
	}
	out := make([]string, 0, c.Len())
	for _, trozo := range c.Data().Chunks() {
		a, ok := trozo.(*array.Decimal128)
		if !ok {
			return nil, fmt.Errorf("%s no es decimal128 sino %s", c.Name(), c.DataType())
		}
		for i := 0; i < a.Len(); i++ {
			out = append(out, a.Value(i).ToString(tipo.Scale))
		}
	}
	return out, nil
}
