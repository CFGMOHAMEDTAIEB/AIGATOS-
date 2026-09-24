import { alpha, createTheme } from '@mui/material/styles'

const navy = '#081525'
const cobalt = '#2563eb'

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: cobalt, dark: '#1d4ed8', light: '#e8f0ff', contrastText: '#ffffff' },
    secondary: { main: '#06b6d4', dark: '#0891b2', light: '#cffafe', contrastText: navy },
    error: { main: '#dc3444', dark: '#b91c2d', light: '#fff0f2' },
    warning: { main: '#d97706', dark: '#b45309', light: '#fff7e7' },
    success: { main: '#059669', dark: '#047857', light: '#e8faf3' },
    info: { main: '#0284c7', light: '#e8f5ff' },
    background: { default: '#f4f7fb', paper: '#ffffff' },
    divider: '#e3eaf2',
    text: { primary: '#102033', secondary: '#607087' },
  },
  typography: {
    fontFamily: '"Segoe UI Variable", "Segoe UI", Inter, Arial, sans-serif',
    h1: { fontSize: 'clamp(1.85rem, 3vw, 2.7rem)', fontWeight: 780, lineHeight: 1.08, letterSpacing: '-0.045em' },
    h2: { fontSize: '1.25rem', fontWeight: 760, lineHeight: 1.25, letterSpacing: '-0.02em' },
    h3: { fontSize: '1.02rem', fontWeight: 740, lineHeight: 1.35, letterSpacing: '-0.012em' },
    h4: { fontWeight: 780, letterSpacing: '-0.035em' },
    body1: { lineHeight: 1.62 },
    body2: { lineHeight: 1.55 },
    overline: { fontSize: '.7rem', fontWeight: 800, letterSpacing: '.12em', lineHeight: 1.8 },
    button: { textTransform: 'none', fontWeight: 720, letterSpacing: '-0.01em' },
  },
  shape: { borderRadius: 14 },
  components: {
    MuiCssBaseline: { styleOverrides: { body: { backgroundImage: 'radial-gradient(circle at 88% 0%, rgba(37,99,235,.07), transparent 27%), linear-gradient(180deg,#f8faff 0,#f4f7fb 360px)' }, '*': { scrollbarWidth: 'thin', scrollbarColor: '#b7c4d3 transparent' } } },
    MuiCard: { defaultProps: { elevation: 0 }, styleOverrides: { root: { border: '1px solid #e1e8f0', boxShadow: '0 8px 28px rgba(8,21,37,.055)', borderRadius: 18, backgroundImage: 'linear-gradient(180deg,rgba(255,255,255,1),rgba(252,253,255,.98))', transition: 'border-color .2s ease, box-shadow .2s ease, transform .2s ease' } } },
    MuiCardContent: { styleOverrides: { root: { padding: 24, '&:last-child': { paddingBottom: 24 } } } },
    MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { root: { backgroundImage: 'none' }, outlined: { borderColor: '#e1e8f0' } } },
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { borderRadius: 11, minHeight: 40, paddingInline: 18, transition: 'transform .15s ease, box-shadow .15s ease, background-color .15s ease' }, contained: { boxShadow: `0 7px 18px ${alpha(cobalt,.22)}`, '&:hover': { boxShadow: `0 10px 24px ${alpha(cobalt,.28)}`, transform: 'translateY(-1px)' } }, outlined: { borderWidth: 1.5, '&:hover': { borderWidth: 1.5, backgroundColor: alpha(cobalt,.045) } } } },
    MuiIconButton: { styleOverrides: { root: { borderRadius: 10 } } },
    MuiChip: { styleOverrides: { root: { height: 28, borderRadius: 9, fontWeight: 720, fontSize: '.75rem' }, filledPrimary: { background: 'linear-gradient(135deg,#2563eb,#1d4ed8)' } } },
    MuiAlert: { styleOverrides: { root: { borderRadius: 14, border: '1px solid transparent' }, standardWarning: { borderColor: '#f3d7a5' }, standardSuccess: { borderColor: '#b8e5d4' }, standardInfo: { borderColor: '#b9ddf2' }, standardError: { borderColor: '#f0c0c6' } } },
    MuiTableContainer: { styleOverrides: { root: { border: '1px solid #e1e8f0', borderRadius: 16, boxShadow: '0 7px 24px rgba(8,21,37,.045)' } } },
    MuiTableCell: { styleOverrides: { root: { borderBottomColor: '#e8edf3', paddingBlock: 14 }, head: { color: '#405269', fontSize: '.72rem', letterSpacing: '.045em', textTransform: 'uppercase' } } },
    MuiTableRow: { styleOverrides: { root: { '&:last-child td': { borderBottom: 0 }, '&.MuiTableRow-hover:hover': { backgroundColor: '#f4f8ff' } } } },
    MuiTextField: { defaultProps: { variant: 'outlined' } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 12, backgroundColor: '#fbfcfe', '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#9bb8dd' }, '&.Mui-focused': { backgroundColor: '#fff', boxShadow: `0 0 0 4px ${alpha(cobalt,.09)}` } } } },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 20, border: '1px solid #e1e8f0', boxShadow: '0 30px 80px rgba(8,21,37,.22)' } } },
    MuiTooltip: { styleOverrides: { tooltip: { backgroundColor: navy, borderRadius: 8, fontSize: '.72rem' } } },
  },
})
