import js from '@eslint/js'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['src/**/*.{js,jsx}', 'vite.config.js'],
    languageOptions: {
      ecmaVersion: 'latest', sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    rules: { ...js.configs.recommended.rules, 'no-unused-vars': 'off' },
  },
]
