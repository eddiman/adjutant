import type {ReactNode} from 'react';
import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import BrowserOnly from '@docusaurus/BrowserOnly';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './index.module.css';

/* ─── Hero Section ──────────────────────────────────────── */

function HeroContent() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <section
      className={styles.hero}>
      {/* Left: text overlay */}
      <div className={styles.heroText}>
        <p className={styles.heroLabel}>Personal AI Agent Framework</p>
        <Heading as="h1" className={styles.heroTitle}>
          {siteConfig.title}
        </Heading>
        <p className={styles.heroSubtitle}>
          A persistent agent that runs on your machine and stays in contact with
          you through Telegram. Knowledge bases, autonomous monitoring, and
          long-term memory — entirely private.
        </p>
        <div className={styles.heroCta}>
          <Link
            className={clsx('button button--lg', styles.btnPrimary)}
            to="/docs/getting-started/installation">
            Get Started
          </Link>
          <Link
            className={clsx('button button--lg button--outline', styles.btnOutline)}
            to="/docs/intro">
            Learn More
          </Link>
        </div>
        <div className={styles.installBlock}>
          <code className={styles.installCmd}>
            $ git clone https://github.com/eddiman/adjutant.git
          </code>
        </div>
      </div>

      {/* Right: 3D wobbling sphere */}
      <div className={styles.heroCanvas}>
        <BrowserOnly fallback={<div className={styles.canvasPlaceholder} />}>
          {() => {
            const WobblingScene =
              require('../components/WobblingScene').default;
            return <WobblingScene />;
          }}
        </BrowserOnly>
      </div>
    </section>
  );
}

/* ─── Features Section ──────────────────────────────────── */

type FeatureItem = {
  title: string;
  description: string;
  icon: string;
};

const features: FeatureItem[] = [
  {
    title: 'Telegram Interface',
    icon: '>_',
    description:
      'Send messages, commands, and photos through Telegram. Adjutant responds with full LLM reasoning.',
  },
  {
    title: 'Knowledge Bases',
    icon: 'KB',
    description:
      'Sandboxed sub-agent workspaces for domain-specific knowledge. Each KB runs in isolation with its own permissions.',
  },
  {
    title: 'Autonomous Monitoring',
    icon: '~',
    description:
      'Scheduled pulse checks and deep reviews scan your projects and notify you when something needs attention.',
  },
  {
    title: 'Privacy First',
    icon: '#',
    description:
      'Runs entirely on your machine. No server, no cloud. Data only leaves your device through the messages you send.',
  },
  {
    title: 'Extensible',
    icon: '+',
    description:
      'Backend-agnostic messaging adaptor, pluggable capabilities, and a three-layer identity model you control.',
  },
  {
    title: 'Memory & Learning',
    icon: '{}',
    description:
      'Persistent long-term memory with auto-classification. Remembers corrections, decisions, and patterns.',
  },
];

function Feature({title, description, icon}: FeatureItem) {
  return (
    <div className={styles.featureCard}>
      <div className={styles.featureIcon}>
        <span>{icon}</span>
      </div>
      <Heading as="h3" className={styles.featureTitle}>
        {title}
      </Heading>
      <p className={styles.featureDesc}>{description}</p>
    </div>
  );
}

function FeaturesSection() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2">Capabilities</Heading>
          <p>
            Everything you need in a personal AI agent, running entirely on your
            hardware.
          </p>
        </div>
        <div className={styles.featuresGrid}>
          {features.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─── How It Works ──────────────────────────────────────── */

type StepItem = {
  step: string;
  title: string;
  description: string;
};

const steps: StepItem[] = [
  {
    step: '01',
    title: 'You send a message',
    description:
      'Open Telegram and type a message or command. Send photos for vision analysis, or use slash commands for specific tasks.',
  },
  {
    step: '02',
    title: 'Adjutant processes it',
    description:
      'The dispatcher routes your input — slash commands go to handlers, natural language goes through AI reasoning with full context.',
  },
  {
    step: '03',
    title: 'You get a response',
    description:
      'Adjutant replies in Telegram with structured answers, code analysis, knowledge base queries, or monitoring alerts.',
  },
];

function HowItWorks() {
  return (
    <section className={styles.howItWorks}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2">How It Works</Heading>
          <p>Three steps from message to response.</p>
        </div>
        <div className={styles.stepsGrid}>
          {steps.map((s, idx) => (
            <div key={idx} className={styles.stepCard}>
              <span className={styles.stepNumber}>{s.step}</span>
              <Heading as="h3" className={styles.stepTitle}>
                {s.title}
              </Heading>
              <p className={styles.stepDesc}>{s.description}</p>
            </div>
          ))}
        </div>
        <div className={styles.stepsCta}>
          <Link
            className="button button--outline button--primary button--lg"
            to="/docs/architecture/overview">
            Architecture Overview
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ─── Bottom CTA ────────────────────────────────────────── */

function BottomCta() {
  return (
    <section className={styles.bottomCta}>
      <div className="container">
        <Heading as="h2" className={styles.ctaTitle}>
          Ready to get started?
        </Heading>
        <p className={styles.ctaSubtitle}>
          Set up Adjutant in under five minutes. All you need is a Mac or Linux
          machine, a Telegram account, and an API key.
        </p>
        <div className={styles.ctaButtons}>
          <Link
            className={clsx('button button--lg', styles.btnPrimary)}
            to="/docs/getting-started/installation">
            Installation Guide
          </Link>
          <Link
            className="button button--lg button--outline button--secondary"
            to="/docs/guides/commands">
            Browse Commands
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ─── Page ──────────────────────────────────────────────── */

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={`${siteConfig.title} — Personal AI Agent Framework`}
      description="A persistent personal AI agent framework that runs on your machine and communicates through Telegram.">
      <HeroContent />
      <main>
        <FeaturesSection />
        <HowItWorks />
        <BottomCta />
      </main>
    </Layout>
  );
}
