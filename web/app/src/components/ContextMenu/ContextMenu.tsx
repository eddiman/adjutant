import { useCallback, useEffect, useRef, useState } from 'react';
import styles from './ContextMenu.module.css';

export interface ContextMenuItem {
  label: string;
  icon?: React.ReactNode;
  shortcut?: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  divider?: boolean;
  submenu?: ContextMenuItem[];
  colorBadge?: string; // CSS color for color picker badges
}

interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

// Detect if device is touch-only
const isTouchDevice = () => {
  if (typeof window === 'undefined') return false;
  return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
};

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const [openSubmenu, setOpenSubmenu] = useState<number | null>(null);
  const [adjustedPosition, setAdjustedPosition] = useState({ x, y });
  const isTouch = useRef(isTouchDevice());
  
  // Store items in a ref so native event listeners can access current values
  const itemsRef = useRef(items);
  const onCloseRef = useRef(onClose);
  
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);
  
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Adjust position to stay within viewport
  useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      let newX = x;
      let newY = y;
      
      // Adjust horizontal position if menu goes off-screen
      if (rect.right > window.innerWidth) {
        newX = x - rect.width;
      }
      
      // Adjust vertical position if menu goes off-screen
      if (rect.bottom > window.innerHeight) {
        newY = y - rect.height;
      }
      
      if (newX !== x || newY !== y) {
        setAdjustedPosition({ x: newX, y: newY });
      }
    }
  }, [x, y]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Native touch event listeners for iOS reliability
  useEffect(() => {
    const menu = menuRef.current;
    const backdrop = backdropRef.current;
    if (!menu || !backdrop) return;

    // Handle backdrop touch to close menu
    const handleBackdropTouch = (e: TouchEvent) => {
      e.preventDefault();
      e.stopPropagation();
      onCloseRef.current();
    };

    // Handle button touches - find and activate the tapped item
    const handleMenuTouch = (e: TouchEvent) => {
      const target = e.target as HTMLElement;
      const button = target.closest(`button.${styles['context-menu-item']}`) as HTMLButtonElement | null;
      
      if (!button) return;
      
      e.preventDefault();
      e.stopPropagation();
      
      // Find the item index from the button's data attribute
      const itemIndex = button.dataset.itemIndex;
      const subItemIndex = button.dataset.subItemIndex;
      
      if (itemIndex !== undefined) {
        const idx = parseInt(itemIndex, 10);
        const item = itemsRef.current[idx];
        
        if (subItemIndex !== undefined) {
          // It's a submenu item
          const subIdx = parseInt(subItemIndex, 10);
          const subItem = item?.submenu?.[subIdx];
          if (subItem && !subItem.disabled) {
            subItem.onClick();
            onCloseRef.current();
          }
        } else {
          // It's a main menu item
          if (item && !item.disabled && !item.submenu) {
            item.onClick();
            onCloseRef.current();
          }
        }
      }
    };

    backdrop.addEventListener('touchend', handleBackdropTouch, { passive: false });
    menu.addEventListener('touchend', handleMenuTouch, { passive: false });

    return () => {
      backdrop.removeEventListener('touchend', handleBackdropTouch);
      menu.removeEventListener('touchend', handleMenuTouch);
    };
  }, []);

  const handleItemClick = useCallback((item: ContextMenuItem, index: number) => {
    if (item.disabled) return;
    
    // For touch devices, clicking on a submenu parent toggles it
    if (item.submenu) {
      if (isTouch.current) {
        setOpenSubmenu(openSubmenu === index ? null : index);
      }
      return;
    }
    
    item.onClick();
    onClose();
  }, [onClose, openSubmenu]);

  const handleSubmenuItemClick = useCallback((item: ContextMenuItem) => {
    if (item.disabled) return;
    item.onClick();
    onClose();
  }, [onClose]);

  const handleItemMouseEnter = useCallback((index: number, item: ContextMenuItem) => {
    // On touch devices, don't use hover - use click instead
    if (isTouch.current) return;
    
    if (item.submenu && !item.disabled) {
      setOpenSubmenu(index);
    } else {
      setOpenSubmenu(null);
    }
  }, []);

  return (
    <>
      {/* Invisible backdrop to catch outside clicks/taps */}
      <div 
        ref={backdropRef}
        className={styles['context-menu-backdrop']}
        onClick={onClose}
      />
      
      <div
        ref={menuRef}
        className={styles['context-menu']}
        style={{ left: adjustedPosition.x, top: adjustedPosition.y }}
        onContextMenu={(e) => e.preventDefault()}
      >
        {items.map((item, index) => (
          item.divider ? (
            <div key={index} className={styles['context-menu-divider']} />
          ) : (
            <div key={index} className={styles['context-menu-item-wrapper']}>
              <button
                data-item-index={index}
                className={`${styles['context-menu-item']} ${item.disabled ? styles.disabled : ''} ${item.danger ? styles.danger : ''} ${item.submenu ? styles['has-submenu'] : ''}`}
                onClick={() => handleItemClick(item, index)}
                onMouseEnter={() => handleItemMouseEnter(index, item)}
                disabled={item.disabled && !item.submenu}
              >
                {item.icon && <span className={styles['context-menu-icon']}>{item.icon}</span>}
                <span className={styles['context-menu-label']}>{item.label}</span>
                {item.shortcut && <span className={styles['context-menu-shortcut']}>{item.shortcut}</span>}
                {item.submenu && (
                  <span className={styles['context-menu-arrow']}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </span>
                )}
              </button>
              
              {/* Submenu - positioned via CSS relative to parent */}
              {item.submenu && openSubmenu === index && (
                <div className={`${styles['context-menu']} ${styles['context-submenu']}`}>
                  {item.submenu.map((subItem, subIndex) => (
                    subItem.divider ? (
                      <div key={subIndex} className={styles['context-menu-divider']} />
                    ) : (
                      <button
                        key={subIndex}
                        data-item-index={index}
                        data-sub-item-index={subIndex}
                        className={`${styles['context-menu-item']} ${subItem.disabled ? styles.disabled : ''} ${subItem.danger ? styles.danger : ''}`}
                        onClick={() => handleSubmenuItemClick(subItem)}
                        disabled={subItem.disabled}
                      >
                        {subItem.colorBadge && (
                          <span 
                            className={styles['context-menu-color-badge']} 
                            style={{ backgroundColor: subItem.colorBadge }}
                          />
                        )}
                        {subItem.icon && <span className={styles['context-menu-icon']}>{subItem.icon}</span>}
                        <span className={styles['context-menu-label']}>{subItem.label}</span>
                        {subItem.shortcut && <span className={styles['context-menu-shortcut']}>{subItem.shortcut}</span>}
                      </button>
                    )
                  ))}
                </div>
              )}
            </div>
          )
        ))}
      </div>
    </>
  );
}
