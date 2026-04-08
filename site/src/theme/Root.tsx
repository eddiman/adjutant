import React, {useLayoutEffect, useRef} from 'react';
import {useLocation} from '@docusaurus/router';

export default function Root({children}: {children: React.ReactNode}) {
  const {pathname} = useLocation();
  const wrapperRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    el.classList.remove('page-enter');
    void el.offsetWidth;
    el.classList.add('page-enter');
  }, [pathname]);

  return (
    <div ref={wrapperRef} className="page-enter">
      {children}
    </div>
  );
}
