// SPDX-FileCopyrightText: 2024 Samuele Musiani <samu@teapot.ovh>
//
// SPDX-License-Identifier: AGPL-3.0-only

package config

import (
	"embed"
	"io/fs"
)

//go:embed *.json
var content embed.FS

func Open(path string) (fs.File, error) {
	return content.Open(path)
}

func ReadFile(path string) ([]byte, error) {
	return content.ReadFile(path)
}
