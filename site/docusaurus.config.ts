import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Adjutant',
  tagline: 'A persistent personal AI agent framework',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  url: 'https://eddiman.github.io',
  baseUrl: '/adjutant-docs/',

  organizationName: 'eddiman',
  projectName: 'adjutant-docs',
  deploymentBranch: 'gh-pages',
  trailingSlash: false,

  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/eddiman/adjutant/tree/main/docs/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/adjutant-social-card.png',
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Adjutant',
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/docs/guides/configuration',
          label: 'Guides',
          position: 'left',
        },
        {
          to: '/docs/architecture/overview',
          label: 'Architecture',
          position: 'left',
        },
        {
          to: '/docs/development/contributing',
          label: 'Development',
          position: 'left',
        },

        {
          href: 'https://github.com/eddiman/adjutant',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Getting Started',
          items: [
            {label: 'Installation', to: '/docs/getting-started/installation'},
            {label: 'Setup Wizard', to: '/docs/getting-started/setup-wizard'},
            {label: 'First Message', to: '/docs/getting-started/first-message'},
          ],
        },
        {
          title: 'Guides',
          items: [
            {label: 'Commands', to: '/docs/guides/commands'},
            {label: 'Knowledge Bases', to: '/docs/guides/knowledge-bases'},
            {label: 'Configuration', to: '/docs/guides/configuration'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'GitHub', href: 'https://github.com/eddiman/adjutant'},
          ],
        },
      ],
      copyright: `Copyright \u00A9 ${new Date().getFullYear()} Adjutant. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'bash', 'yaml', 'toml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
