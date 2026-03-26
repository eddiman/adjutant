import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/telegram-setup',
        'getting-started/setup-wizard',
        'getting-started/first-message',
      ],
    },
    {
      type: 'category',
      label: 'User Guides',
      items: [
        'guides/configuration',
        'guides/commands',
        'guides/knowledge-bases',
        'guides/backends',
        'guides/schedules',
        'guides/autonomy',
        'guides/lifecycle',
        'guides/memory',
        'guides/news',
        'guides/troubleshooting',
      ],
    },
    {
      type: 'category',
      label: 'Architecture',
      items: [
        'architecture/overview',
        'architecture/messaging',
        'architecture/identity',
        'architecture/state',
        'architecture/autonomy',
        'architecture/backends',
        'architecture/design-decisions',
      ],
    },
    {
      type: 'category',
      label: 'Development',
      items: [
        'development/contributing',
        'development/adaptor-guide',
        'development/plugin-guide',
        'development/backend-guide',
        'development/testing',
        'development/setup-wizard-internals',
      ],
    },
  ],
};

export default sidebars;
