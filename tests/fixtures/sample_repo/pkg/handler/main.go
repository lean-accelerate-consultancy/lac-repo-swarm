package handler

import (
	"fmt"
	"net/http"
)

// Handler processes HTTP requests
type Handler struct {
	Name string
}

// ServeHTTP handles incoming requests
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "Hello from %s", h.Name)
}
