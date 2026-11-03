export type ButtonVariant = 'primary' | 'secondary' | 'text' | 'danger';
export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
export type IconName = 'buscar' | 'persona' | 'personas' | 'proyecto' | 'universidad'
  | 'organizacion' | 'verificado' | 'investigacion' | 'correo' | 'telefono' | 'externo'
  | 'calendario' | 'tiempo' | 'filtro' | 'flecha' | 'cerrar' | 'menu' | 'mas'
  | 'informacion' | 'alerta' | 'comprobar' | 'candado' | 'editar' | 'renovar';

export function descriptionIds(...values: unknown[]): string | undefined {
  const ids = values.flatMap(value => typeof value === 'string' ? value.split(/\s+/).filter(Boolean) : []);
  return ids.length ? [...new Set(ids)].join(' ') : undefined;
}
